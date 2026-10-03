// JNI bridge for Tiny Clinic: load a GGUF model, then turn a health worker's note into a
// compact case record under a GBNF grammar, reporting the probability of every token chosen.
//
// One model and one context at a time; LlamaEngine.kt calls in from a single thread.

#include <android/log.h>
#include <jni.h>

#include <algorithm>
#include <chrono>
#include <cmath>
#include <cstdio>
#include <sstream>
#include <string>
#include <vector>

#include "chat.h"
#include "common.h"
#include "llama.h"

#define TAG "TinyClinicLlama"
#define LOGI(...) __android_log_print(ANDROID_LOG_INFO, TAG, __VA_ARGS__)
#define LOGE(...) __android_log_print(ANDROID_LOG_ERROR, TAG, __VA_ARGS__)

namespace {

constexpr int BATCH_SIZE = 512;

llama_model *g_model = nullptr;
llama_context *g_ctx = nullptr;
llama_batch g_batch{};
bool g_has_batch = false;
common_chat_templates_ptr g_templates;
std::vector<llama_token> g_cached;          // tokens held in the KV cache, sequence 0
std::vector<llama_token_data> g_candidates;  // reused between sampling steps

void log_to_logcat(ggml_log_level level, const char *text, void *) {
    if (level == GGML_LOG_LEVEL_DEBUG) return;
    const int prio = level == GGML_LOG_LEVEL_ERROR ? ANDROID_LOG_ERROR
                   : level == GGML_LOG_LEVEL_WARN  ? ANDROID_LOG_WARN
                                                   : ANDROID_LOG_INFO;
    __android_log_write(prio, TAG, text);
}

long long now_ms() {
    using namespace std::chrono;
    return duration_cast<milliseconds>(steady_clock::now().time_since_epoch()).count();
}

std::string utf8(JNIEnv *env, jbyteArray bytes) {
    const jsize n = env->GetArrayLength(bytes);
    std::string out(static_cast<size_t>(n), '\0');
    env->GetByteArrayRegion(bytes, 0, n, reinterpret_cast<jbyte *>(out.data()));
    return out;
}

jbyteArray to_bytes(JNIEnv *env, const std::string &s) {
    jbyteArray out = env->NewByteArray(static_cast<jsize>(s.size()));
    env->SetByteArrayRegion(out, 0, static_cast<jsize>(s.size()), reinterpret_cast<const jbyte *>(s.data()));
    return out;
}

std::string json_escape(const std::string &s) {
    std::string out;
    for (const unsigned char c : s) {
        switch (c) {
            case '"':  out += "\\\""; break;
            case '\\': out += "\\\\"; break;
            case '\n': out += "\\n";  break;
            case '\r': out += "\\r";  break;
            case '\t': out += "\\t";  break;
            default:
                if (c < 0x20) {
                    char buf[8];
                    snprintf(buf, sizeof buf, "\\u%04x", c);
                    out += buf;
                } else {
                    out += static_cast<char>(c);  // UTF-8 passes through; Kotlin decodes it
                }
        }
    }
    return out;
}

jbyteArray error_json(JNIEnv *env, const std::string &message) {
    LOGE("%s", message.c_str());
    return to_bytes(env, "{\"error\":\"" + json_escape(message) + "\"}");
}

void free_model() {
    g_templates.reset();
    if (g_has_batch) { llama_batch_free(g_batch); g_has_batch = false; }
    if (g_ctx) { llama_free(g_ctx); g_ctx = nullptr; }
    if (g_model) { llama_model_free(g_model); g_model = nullptr; }
    g_cached.clear();
}

// Decode `tokens` at positions start_pos.., asking for logits on the last one only.
bool decode(const std::vector<llama_token> &tokens, int start_pos) {
    for (size_t i = 0; i < tokens.size(); i += BATCH_SIZE) {
        const size_t n = std::min(tokens.size() - i, static_cast<size_t>(BATCH_SIZE));
        common_batch_clear(g_batch);
        for (size_t j = 0; j < n; j++) {
            const bool last = i + j == tokens.size() - 1;
            common_batch_add(g_batch, tokens[i + j], start_pos + static_cast<int>(i + j), {0}, last);
        }
        if (llama_decode(g_ctx, g_batch) != 0) return false;
    }
    return true;
}

// Greedy choice among the tokens the grammar allows. `p` is the chosen token's probability
// within that allowed set: how sure the model was, given that it had to write a valid record.
llama_token pick(llama_sampler *grammar, float *p) {
    const llama_vocab *vocab = llama_model_get_vocab(g_model);
    const int n_vocab = llama_vocab_n_tokens(vocab);
    const float *logits = llama_get_logits_ith(g_ctx, -1);
    g_candidates.resize(static_cast<size_t>(n_vocab));
    for (llama_token id = 0; id < n_vocab; id++) g_candidates[id] = {id, logits[id], 0.0f};
    llama_token_data_array cur = {g_candidates.data(), g_candidates.size(), -1, false};
    llama_sampler_apply(grammar, &cur);  // disallowed tokens get -inf

    size_t best = cur.size;
    float max_logit = -INFINITY;
    for (size_t i = 0; i < cur.size; i++) {
        if (cur.data[i].logit > max_logit) { max_logit = cur.data[i].logit; best = i; }
    }
    if (best == cur.size || !std::isfinite(max_logit)) return LLAMA_TOKEN_NULL;
    double sum = 0.0;
    for (size_t i = 0; i < cur.size; i++) {
        if (std::isfinite(cur.data[i].logit)) sum += std::exp(static_cast<double>(cur.data[i].logit) - max_logit);
    }
    *p = static_cast<float>(1.0 / sum);
    return cur.data[best].id;
}

}  // namespace

extern "C" JNIEXPORT void JNICALL
Java_org_tinyclinic_llama_LlamaNative_init(JNIEnv *env, jobject, jstring jlib_dir) {
    llama_log_set(log_to_logcat, nullptr);
    const char *lib_dir = env->GetStringUTFChars(jlib_dir, nullptr);
    LOGI("Loading ggml backends from %s", lib_dir);
    ggml_backend_load_all_from_path(lib_dir);  // picks the best CPU variant for this phone
    env->ReleaseStringUTFChars(jlib_dir, lib_dir);
    llama_backend_init();
}

extern "C" JNIEXPORT jstring JNICALL
Java_org_tinyclinic_llama_LlamaNative_systemInfo(JNIEnv *env, jobject) {
    return env->NewStringUTF(llama_print_system_info());
}

extern "C" JNIEXPORT jstring JNICALL
Java_org_tinyclinic_llama_LlamaNative_load(JNIEnv *env, jobject, jstring jpath, jint n_ctx, jint n_threads) {
    free_model();
    const char *path = env->GetStringUTFChars(jpath, nullptr);
    LOGI("Loading model %s (n_ctx %d, %d threads)", path, n_ctx, n_threads);
    g_model = llama_model_load_from_file(path, llama_model_default_params());
    env->ReleaseStringUTFChars(jpath, path);
    if (!g_model) return env->NewStringUTF("could not read the model file");

    llama_context_params params = llama_context_default_params();
    params.n_ctx = static_cast<uint32_t>(n_ctx);
    params.n_batch = BATCH_SIZE;
    params.n_ubatch = BATCH_SIZE;
    params.n_threads = n_threads;
    params.n_threads_batch = n_threads;
    g_ctx = llama_init_from_model(g_model, params);
    if (!g_ctx) {
        free_model();
        return env->NewStringUTF("not enough memory for the model context");
    }
    g_batch = llama_batch_init(BATCH_SIZE, 0, 1);
    g_has_batch = true;
    try {
        g_templates = common_chat_templates_init(g_model, "");
    } catch (const std::exception &e) {
        free_model();
        return env->NewStringUTF((std::string("unusable chat template: ") + e.what()).c_str());
    }
    return env->NewStringUTF("");
}

extern "C" JNIEXPORT jstring JNICALL
Java_org_tinyclinic_llama_LlamaNative_modelDescription(JNIEnv *env, jobject) {
    if (!g_model) return env->NewStringUTF("");
    char desc[256];
    llama_model_desc(g_model, desc, sizeof desc);
    char out[384];
    snprintf(out, sizeof out, "%s, %.2fB params, %.2f GB, context %u", desc,
             static_cast<double>(llama_model_n_params(g_model)) / 1e9,
             static_cast<double>(llama_model_size(g_model)) / 1e9, llama_n_ctx(g_ctx));
    return env->NewStringUTF(out);
}

// Returns UTF-8 JSON: {text, pieces: [[piece, p], ...], complete, prompt_tokens, reused_tokens,
// generated_tokens, prompt_ms, generate_ms}, or {error}.
extern "C" JNIEXPORT jbyteArray JNICALL
Java_org_tinyclinic_llama_LlamaNative_extract(JNIEnv *env, jobject, jbyteArray jsystem, jbyteArray juser,
                                              jbyteArray jgrammar, jint max_tokens) {
    if (!g_ctx) return error_json(env, "no model loaded");
    const long long t0 = now_ms();

    common_chat_templates_inputs inputs;
    common_chat_msg system, user;
    system.role = "system";
    system.content = utf8(env, jsystem);
    user.role = "user";
    user.content = utf8(env, juser);
    inputs.messages = {system, user};
    inputs.add_generation_prompt = true;
    inputs.use_jinja = true;
    inputs.enable_thinking = false;
    std::string prompt;
    try {
        prompt = common_chat_templates_apply(g_templates.get(), inputs).prompt;
    } catch (const std::exception &e) {
        return error_json(env, std::string("chat template failed: ") + e.what());
    }

    const llama_vocab *vocab = llama_model_get_vocab(g_model);
    std::vector<llama_token> tokens = common_tokenize(vocab, prompt, false, true);
    if (llama_vocab_get_add_bos(vocab) && (tokens.empty() || tokens.front() != llama_vocab_bos(vocab))) {
        tokens.insert(tokens.begin(), llama_vocab_bos(vocab));
    }
    if (static_cast<int>(tokens.size()) + max_tokens > static_cast<int>(llama_n_ctx(g_ctx))) {
        return error_json(env, "the note is too long for the model context");
    }

    // The instructions are the same every time: keep their cache, decode only what changed.
    size_t reused = 0;
    while (reused < tokens.size() && reused < g_cached.size() && tokens[reused] == g_cached[reused]) reused++;
    if (reused == tokens.size()) reused--;  // decode at least one token to get fresh logits
    llama_memory_t memory = llama_get_memory(g_ctx);
    if (!llama_memory_seq_rm(memory, 0, static_cast<llama_pos>(reused), -1)) {
        llama_memory_clear(memory, true);  // recurrent models cannot drop a suffix
        reused = 0;
    }
    g_cached.assign(tokens.begin(), tokens.begin() + static_cast<long>(reused));
    if (!decode(std::vector<llama_token>(tokens.begin() + static_cast<long>(reused), tokens.end()),
                static_cast<int>(reused))) {
        llama_memory_clear(memory, true);
        g_cached.clear();
        return error_json(env, "llama_decode failed on the prompt");
    }
    g_cached = tokens;
    const long long t1 = now_ms();

    const std::string grammar_text = utf8(env, jgrammar);
    llama_sampler *grammar = llama_sampler_init_grammar(vocab, grammar_text.c_str(), "root");
    if (!grammar) return error_json(env, "the grammar does not parse");

    std::string text;
    std::ostringstream pieces;
    pieces.precision(6);
    int generated = 0;
    bool complete = false;
    std::string failure;
    while (generated < max_tokens) {
        float p = 0.0f;
        const llama_token id = pick(grammar, &p);
        if (id == LLAMA_TOKEN_NULL) { failure = "no token fits the grammar"; break; }
        if (llama_vocab_is_eog(vocab, id)) { complete = true; break; }
        llama_sampler_accept(grammar, id);
        const std::string piece = common_token_to_piece(vocab, id, false);
        text += piece;
        pieces << (generated ? "," : "") << "[\"" << json_escape(piece) << "\"," << p << "]";
        generated++;
        common_batch_clear(g_batch);
        common_batch_add(g_batch, id, static_cast<llama_pos>(g_cached.size()), {0}, true);
        if (llama_decode(g_ctx, g_batch) != 0) { failure = "llama_decode failed while writing"; break; }
        g_cached.push_back(id);
    }
    llama_sampler_free(grammar);
    if (!failure.empty()) {
        llama_memory_clear(memory, true);
        g_cached.clear();
        return error_json(env, failure);
    }
    const long long t2 = now_ms();

    std::ostringstream out;
    out << "{\"text\":\"" << json_escape(text) << "\",\"pieces\":[" << pieces.str() << "]"
        << ",\"complete\":" << (complete ? "true" : "false")
        << ",\"prompt_tokens\":" << tokens.size() << ",\"reused_tokens\":" << reused
        << ",\"generated_tokens\":" << generated << ",\"prompt_ms\":" << (t1 - t0)
        << ",\"generate_ms\":" << (t2 - t1) << "}";
    return to_bytes(env, out.str());
}

extern "C" JNIEXPORT void JNICALL
Java_org_tinyclinic_llama_LlamaNative_unload(JNIEnv *, jobject) {
    free_model();
}

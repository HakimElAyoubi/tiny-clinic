package org.tinyclinic.llama

import android.content.Context
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.withContext
import org.json.JSONObject

/**
 * On-device llama.cpp for Tiny Clinic: load a GGUF model, then turn a health worker's note
 * into a compact case record under a GBNF grammar. Every native call runs on one thread.
 */
class LlamaEngine private constructor(private val nativeLibDir: String) {

    data class Piece(val text: String, val probability: Float)

    data class Extraction(
        val text: String,
        val pieces: List<Piece>,
        val complete: Boolean,   // the grammar finished, so the record is whole
        val promptTokens: Int,
        val reusedTokens: Int,   // prompt tokens served from the cache
        val generatedTokens: Int,
        val promptMs: Long,
        val generateMs: Long,
    )

    @OptIn(ExperimentalCoroutinesApi::class)
    private val llamaThread = Dispatchers.IO.limitedParallelism(1)
    private var started = false

    private suspend fun <T> onLlamaThread(block: () -> T): T = withContext(llamaThread) {
        if (!started) {
            LlamaNative.init(nativeLibDir)
            started = true
        }
        block()
    }

    suspend fun systemInfo(): String = onLlamaThread { LlamaNative.systemInfo() }

    /** Loads a model and returns its description; throws IllegalStateException with the reason. */
    suspend fun load(path: String, contextSize: Int = 2048, threads: Int = defaultThreads()): String =
        onLlamaThread {
            val error = LlamaNative.load(path, contextSize, threads)
            check(error.isEmpty()) { error }
            LlamaNative.modelDescription()
        }

    suspend fun extract(system: String, user: String, grammar: String, maxTokens: Int = 64): Extraction =
        onLlamaThread {
            val raw = LlamaNative.extract(system.toByteArray(), user.toByteArray(), grammar.toByteArray(), maxTokens)
            val json = JSONObject(String(raw, Charsets.UTF_8))
            check(!json.has("error")) { json.getString("error") }
            val pieces = json.getJSONArray("pieces").let { array ->
                List(array.length()) { i ->
                    val piece = array.getJSONArray(i)
                    Piece(piece.getString(0), piece.getDouble(1).toFloat())
                }
            }
            Extraction(
                text = json.getString("text"),
                pieces = pieces,
                complete = json.getBoolean("complete"),
                promptTokens = json.getInt("prompt_tokens"),
                reusedTokens = json.getInt("reused_tokens"),
                generatedTokens = json.getInt("generated_tokens"),
                promptMs = json.getLong("prompt_ms"),
                generateMs = json.getLong("generate_ms"),
            )
        }

    suspend fun unload() = onLlamaThread { LlamaNative.unload() }

    companion object {
        @Volatile
        private var instance: LlamaEngine? = null

        fun get(context: Context): LlamaEngine = instance ?: synchronized(this) {
            instance ?: LlamaEngine(context.applicationInfo.nativeLibraryDir).also { instance = it }
        }

        fun defaultThreads() = (Runtime.getRuntime().availableProcessors() - 2).coerceIn(2, 4)
    }
}

/** JNI entry points, implemented in src/main/cpp/tiny_clinic.cpp. */
internal object LlamaNative {
    init {
        System.loadLibrary("tinyclinic")
    }

    external fun init(nativeLibDir: String)
    external fun systemInfo(): String
    external fun load(path: String, contextSize: Int, threads: Int): String
    external fun modelDescription(): String
    external fun extract(system: ByteArray, user: ByteArray, grammar: ByteArray, maxTokens: Int): ByteArray
    external fun unload()
}

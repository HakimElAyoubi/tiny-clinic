package org.tinyclinic.app

import android.app.Application
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch
import org.tinyclinic.app.engine.Decision
import org.tinyclinic.app.engine.Messages
import org.tinyclinic.app.engine.Rules
import org.tinyclinic.llama.LlamaEngine
import java.io.File

class AppViewModel(app: Application) : AndroidViewModel(app) {

    enum class Step { NOTE, READING, QUESTION, RESULT }

    /** One danger sign on the result screen: its state, and where that came from. */
    data class SignLine(val id: String, val present: Boolean, val text: String, val source: String)

    data class UiState(
        val engineReady: Boolean = false,
        val cpuFeatures: List<String> = emptyList(),
        val modelFolder: String = "",
        val modelName: String? = null,
        val modelDescription: String? = null,
        val modelReady: Boolean = false,
        val status: String = "Starting the on-device engine…",
        val language: String = "ary-Latn",
        val step: Step = Step.NOTE,
        val note: String = "",
        val question: Messages.Question? = null,
        val result: Messages.Rendered? = null,
        val decision: Decision? = null,
        val record: String = "",
        val reading: CheckFlow.Reading? = null,
        val readError: String? = null,
        val signs: List<SignLine> = emptyList(),
    )

    val rules: Rules = Rules.load(app)
    private val llama = LlamaEngine.get(app)
    private val flow = CheckFlow(rules)

    // App-specific storage: a model can be side-loaded here (adb push) without any permission.
    private val modelFolder: File = app.getExternalFilesDir(null) ?: app.filesDir

    private val _state = MutableStateFlow(UiState(modelFolder = modelFolder.path))
    val state = _state.asStateFlow()

    val languages: List<Messages> = rules.templates.values.map { Messages(it) }
        .sortedBy { listOf("ary-Latn", "ary-Arab", "fr", "sw", "en").indexOf(it.language) }

    fun messages(): Messages = Messages(rules.templates.getValue(_state.value.language))

    init {
        viewModelScope.launch { startEngine() }
    }

    fun setLanguage(code: String) {
        _state.update { it.copy(language = code) }
        if (_state.value.step != Step.NOTE) show()
    }

    fun setNote(text: String) = _state.update { it.copy(note = text) }

    fun check() {
        val note = _state.value.note.trim()
        _state.update { it.copy(step = Step.READING, readError = null) }
        viewModelScope.launch {
            val extraction = if (_state.value.modelReady && note.isNotEmpty()) {
                runCatching { llama.extract(rules.systemPrompt, rules.userPrefix + note, rules.grammar) }
                    .onFailure { error -> _state.update { it.copy(readError = error.message) } }
                    .getOrNull()
            } else null
            flow.start(extraction)
            show()
        }
    }

    fun answer(value: Any?) {
        val slot = flow.nextQuestion() ?: return
        flow.answer(slot, value)
        show()
    }

    fun change(slot: String) {
        flow.change(slot)
        show()
    }

    fun newCheck() = _state.update {
        it.copy(step = Step.NOTE, note = "", question = null, result = null, decision = null, record = "", reading = null)
    }

    private fun show() {
        val messages = messages()
        val slot = flow.nextQuestion()
        _state.update {
            if (slot != null) {
                it.copy(step = Step.QUESTION, question = messages.question(slot), reading = flow.reading)
            } else {
                it.copy(step = Step.RESULT, question = null, result = flow.render(messages), decision = flow.decision(),
                    record = flow.record(), reading = flow.reading, signs = signLines(messages))
            }
        }
    }

    private suspend fun startEngine() {
        val info = runCatching { llama.systemInfo() }.getOrElse { error ->
            _state.update { it.copy(status = "The on-device engine did not start: ${error.message}") }
            return
        }
        _state.update { it.copy(engineReady = true, cpuFeatures = enabledFeatures(info)) }
        val model = modelFolder.listFiles { file -> file.extension == "gguf" }?.maxByOrNull { it.lastModified() }
        if (model == null) {
            _state.update { it.copy(status = "No model on this phone: the check asks every question.") }
            return
        }
        _state.update { it.copy(modelName = model.name, status = "Loading ${model.name}…") }
        runCatching { llama.load(model.path) }
            .onSuccess { description ->
                _state.update { it.copy(modelDescription = description, modelReady = true, status = "Ready") }
            }
            .onFailure { error -> _state.update { it.copy(status = "Could not load ${model.name}: ${error.message}") } }
    }

    private fun signLines(messages: Messages): List<SignLine> = rules.signs.map { sign ->
        val o = flow.case.obs.getValue(sign.id)
        val value = o.value as Boolean?
        val source = when {
            o.asked && o.worker == null -> "you: ${messages.notSure}"
            o.asked -> "you"
            o.model != null -> "note" + (o.confidence?.let { " ${(it * 100).toInt()}%" } ?: "")
            else -> "not checked"
        }
        SignLine(sign.id, sign.id in flow.decision().present, messages.signState(sign.id, value), source)
    }

    /** "CPU : NEON = 1 | DOTPROD = 1 | SVE = 0 | ..." -> [NEON, DOTPROD] */
    private fun enabledFeatures(systemInfo: String): List<String> =
        Regex("""([A-Z0-9_]+) = 1""").findAll(systemInfo).map { it.groupValues[1] }.distinct().toList()
}

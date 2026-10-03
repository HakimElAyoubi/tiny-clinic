package org.tinyclinic.app

import org.tinyclinic.app.engine.Case
import org.tinyclinic.app.engine.Confidence
import org.tinyclinic.app.engine.Decision
import org.tinyclinic.app.engine.Messages
import org.tinyclinic.app.engine.Outcome
import org.tinyclinic.app.engine.Record
import org.tinyclinic.app.engine.Rules
import org.tinyclinic.app.engine.decide
import org.tinyclinic.llama.LlamaEngine

/**
 * One danger-sign check, from note to outcome, with no Android in it so it can be tested.
 *
 * read(): the model turns the note into a record (or, without a model, every question is asked)
 * then answer() until outcome() is final.
 */
class CheckFlow(private val rules: Rules) {

    data class Reading(val record: String, val confidence: Map<String, Double>, val extraction: LlamaEngine.Extraction?)

    var case: Case = Case.empty(rules)
        private set
    var reading: Reading? = null
        private set
    private val queue = ArrayDeque<String>()

    /** Start from what the model read; null means no model, so every question will be asked. */
    fun start(extraction: LlamaEngine.Extraction?) {
        queue.clear()
        if (extraction == null || !extraction.complete) {
            case = Case.empty(rules)
            reading = extraction?.let { Reading(it.text, emptyMap(), it) }
        } else {
            val confidence = Confidence.perSlot(extraction.text, extraction.pieces, rules)
            case = Case.fromRecord(extraction.text, rules) { confidence[it] }
            reading = Reading(extraction.text, confidence, extraction)
        }
        refill()
    }

    /** The question to show now, or null when the outcome is final. */
    fun nextQuestion(): String? = queue.firstOrNull()

    fun answer(slot: String, value: Any?) {
        case.answer(slot, value)
        queue.remove(slot)
        if (decide(case, rules).outcome == Outcome.REFER_URGENT) {
            queue.clear() // never delay a referral; the unchecked signs show on the result screen
        } else if (queue.isEmpty()) {
            refill()
        }
    }

    /** Ask a sign again from the result screen, to correct what the tool read. */
    fun change(slot: String) {
        queue.clear()
        queue.add(slot)
    }

    fun decision(): Decision = decide(case, rules)

    fun record(): String = Record.format(case.values(), rules)

    private fun refill() {
        val decision = decide(case, rules)
        if (decision.outcome == Outcome.NEED_INFO) queue.addAll(decision.questions)
    }

    fun render(messages: Messages) = messages.render(decision())
}

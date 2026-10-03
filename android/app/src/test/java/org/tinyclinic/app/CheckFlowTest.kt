package org.tinyclinic.app

import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test
import org.tinyclinic.app.engine.Confidence
import org.tinyclinic.app.engine.Outcome
import org.tinyclinic.app.engine.Rules
import org.tinyclinic.llama.LlamaEngine
import java.io.File

class CheckFlowTest {
    private val rules = Rules(JSONObject(File("src/main/assets/${Rules.ASSET}").readText()))

    /** An extraction as the native code returns it: one piece per character here, all with probability p. */
    private fun extraction(record: String, p: Float = 0.99f, complete: Boolean = true) = LlamaEngine.Extraction(
        text = record, pieces = record.map { LlamaEngine.Piece(it.toString(), p) }, complete = complete,
        promptTokens = 0, reusedTokens = 0, generatedTokens = record.length, promptMs = 0, generateMs = 0,
    )

    @Test
    fun withoutAModelEveryQuestionIsAsked() {
        val flow = CheckFlow(rules)
        flow.start(null)
        val asked = mutableListOf<String>()
        while (true) {
            val slot = flow.nextQuestion() ?: break
            asked += slot
            flow.answer(slot, if (slot == "age") 24 else false)
        }
        assertEquals(listOf("age") + rules.signIds, asked)
        assertEquals(Outcome.NO_DANGER_SIGN, flow.decision().outcome)
    }

    @Test
    fun aPresentAnswerEndsTheQuestions() {
        val flow = CheckFlow(rules)
        flow.start(null)
        flow.answer("age", 18)
        flow.answer("not_able_to_drink", false)
        flow.answer("vomits_everything", true)
        assertNull(flow.nextQuestion())
        val decision = flow.decision()
        assertEquals(Outcome.REFER_URGENT, decision.outcome)
        assertEquals(listOf("convulsions", "lethargic_or_unconscious", "convulsing_now"), decision.pending)
    }

    @Test
    fun aSignInTheNoteRefersWithoutQuestions() {
        val flow = CheckFlow(rules)
        flow.start(extraction("A24 F | C:FEV D2 T38.9 | DRK? VOM1 CNV0 LTH? CNN0"))
        assertNull(flow.nextQuestion())
        assertEquals(Outcome.REFER_URGENT, flow.decision().outcome)
    }

    @Test
    fun confidentReadingNeedsNoQuestions() {
        val flow = CheckFlow(rules)
        flow.start(extraction("A24 F | C:FEV D2 T38.9 | DRK0 VOM0 CNV0 LTH0 CNN0", p = 0.97f))
        assertNull(flow.nextQuestion())
        assertEquals(Outcome.NO_DANGER_SIGN, flow.decision().outcome)
    }

    @Test
    fun unsureReadingIsAsked() {
        val flow = CheckFlow(rules)
        flow.start(extraction("A24 F | C:FEV D2 T38.9 | DRK0 VOM0 CNV0 LTH0 CNN0", p = 0.6f))
        assertEquals("age", flow.nextQuestion())
    }

    @Test
    fun anUnfinishedRecordFallsBackToQuestions() {
        val flow = CheckFlow(rules)
        flow.start(extraction("A24 F | C:FEV", complete = false))
        assertEquals("age", flow.nextQuestion())
    }

    @Test
    fun confidenceTakesTheLowestTokenOfEachValue() {
        val record = "A24 F | C:FEV D2 T38.9 | DRK0 VOM1 CNV? LTH0 CNN0"
        // "A" forced, "24" at 0.8 and 0.95, the rest forced except VOM's value at 0.7
        val pieces = mutableListOf(LlamaEngine.Piece("A", 1f), LlamaEngine.Piece("2", 0.8f), LlamaEngine.Piece("4", 0.95f))
        val rest = record.substring(3)
        val vomValue = record.indexOf("VOM") + 3 - 3
        rest.forEachIndexed { i, c -> pieces += LlamaEngine.Piece(c.toString(), if (i == vomValue) 0.7f else 1f) }
        val confidence = Confidence.perSlot(record, pieces, rules)
        assertEquals(0.8, confidence.getValue("age"), 1e-6)
        assertEquals(0.7, confidence.getValue("vomits_everything"), 1e-6)
        assertEquals(1.0, confidence.getValue("not_able_to_drink"), 1e-6)
    }
}

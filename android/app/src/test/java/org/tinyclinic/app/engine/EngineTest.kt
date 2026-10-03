package org.tinyclinic.app.engine

import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.File

/** The Kotlin engine must agree with the Python one: same rules, same shared test vectors. */
class EngineTest {
    private val rules = Rules(JSONObject(File("src/main/assets/${Rules.ASSET}").readText()))
    private val vectors = JSONArray(javaClass.getResource("/cases.json")!!.readText())

    private fun JSONArray.strings() = List(length()) { getString(it) }

    @Test
    fun sharedVectors() {
        for (i in 0 until vectors.length()) {
            val v = vectors.getJSONObject(i)
            val name = v.getString("name")
            val confidence: (String) -> Double? = when (val c = v.opt("confidence")) {
                is Number -> { _ -> c.toDouble() }
                is JSONObject -> { slot -> if (c.has(slot)) c.getDouble(slot) else c.optDouble("default").takeUnless { it.isNaN() } }
                else -> { _ -> null }
            }
            val case = Case.fromRecord(v.getString("record"), rules, confidence)
            v.optJSONObject("answers")?.let { answers -> answers.keys().forEach { case.answer(it, answers.get(it)) } }
            val decision = decide(case, rules)
            val expect = v.getJSONObject("expect")
            assertEquals(name, expect.getString("outcome"), decision.outcome.name)
            expect.optJSONArray("present")?.let { assertEquals(name, it.strings(), decision.present) }
            expect.optJSONArray("questions")?.let { assertEquals(name, it.strings(), decision.questions) }
            expect.optJSONArray("pending")?.let { assertEquals(name, it.strings(), decision.pending) }
            expect.optJSONArray("reasons")?.let { assertEquals(name, it.strings(), decision.reasons.map { r -> r.first }) }
            expect.optJSONArray("warnings")?.let { assertEquals(name, it.strings(), decision.warnings.map { w -> w.first }) }
        }
    }

    @Test
    fun recordRoundTrip() {
        for (line in listOf(
            "A24 F | C:FEV D2 T38.9 | DRK0 VOM1 CNV? LTH0 CNN0",
            "A? ? | C:? D? T? | DRK? VOM? CNV? LTH? CNN?",
            "A2 M | C:CGH,FEV,DIA,EAR D14 T40.1 | DRK1 VOM1 CNV1 LTH1 CNN1",
        )) {
            assertEquals(line, Record.format(Record.parse(line, rules), rules))
        }
    }

    @Test
    fun everyLanguageRendersEveryMessage() {
        val all = rules.signIds
        for ((language, template) in rules.templates) {
            val messages = Messages(template)
            val refer = messages.render(Decision(Outcome.REFER_URGENT, present = all))
            assertTrue(language, all.all { messages.presentLabel(it) in refer.text })
            val unsure = messages.render(Decision(Outcome.UNSURE, reasons = listOf("not_checked" to mapOf("signs" to all))))
            assertTrue(language, "{" !in unsure.text)
            for (slot in listOf(Case.AGE) + all) assertTrue(language, messages.question(slot).text.isNotBlank())
        }
    }
}

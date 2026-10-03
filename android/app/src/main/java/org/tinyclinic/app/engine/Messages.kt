package org.tinyclinic.app.engine

import org.json.JSONObject

/** The fixed strings of one language (port of engine/templates.py). The model never writes advice. */
class Messages(private val t: JSONObject) {

    data class Option(val value: Any?, val label: String)

    data class Question(val slot: String, val kind: Kind, val text: String, val options: List<Option>) {
        enum class Kind { MONTHS, CHOICE }
    }

    data class Rendered(val outcome: Outcome, val text: String, val warnings: List<String>)

    val language: String = t.getString("language")
    val name: String = t.getString("name")
    val isDraft: Boolean = t.optString("status") == "draft"

    private fun sign(id: String) = t.getJSONObject("signs").getJSONObject(id)

    private fun signs(ids: List<String>, key: String) =
        ids.joinToString(t.getString("list_separator")) { sign(it).getString(key) }

    private fun fill(text: String, params: Map<String, Any>): String =
        params.entries.fold(text) { acc, (key, value) ->
            @Suppress("UNCHECKED_CAST")
            acc.replace("{$key}", if (key == "signs") signs(value as List<String>, "name") else value.toString())
        }

    fun render(decision: Decision): Rendered {
        val outcomes = t.getJSONObject("outcomes")
        val text = when (decision.outcome) {
            Outcome.REFER_URGENT -> outcomes.getString("REFER_URGENT").replace("{signs}", signs(decision.present, "present"))
            Outcome.UNSURE -> outcomes.getString("UNSURE").replace(
                "{reason}",
                decision.reasons.joinToString(" ") { (id, params) -> fill(t.getJSONObject("reasons").getString(id), params) },
            )
            Outcome.NO_DANGER_SIGN -> outcomes.getString("NO_DANGER_SIGN")
            Outcome.NEED_INFO -> throw IllegalArgumentException("NEED_INFO has questions, not a message")
        }
        val warnings = decision.warnings.map { (id, params) -> fill(t.getJSONObject("warnings").getString(id), params) }
        return Rendered(decision.outcome, text, warnings)
    }

    fun question(slot: String): Question {
        val notSure = Option(null, t.getJSONObject("answers").getString("not_sure"))
        if (slot == Case.AGE) {
            return Question(slot, Question.Kind.MONTHS, t.getJSONObject("questions").getString(Case.AGE), listOf(notSure))
        }
        val s = sign(slot)
        return Question(
            slot, Question.Kind.CHOICE, s.getString("question"),
            listOf(Option(true, s.getString("present")), Option(false, s.getString("absent")), notSure),
        )
    }

    /** Label of a sign as found ("Vomits everything"), for the record screen. */
    fun presentLabel(id: String): String = sign(id).getString("present")

    /** How a sign reads on the result screen: its present or absent label, or its name if unknown. */
    fun signState(id: String, value: Boolean?): String = when (value) {
        true -> sign(id).getString("present")
        false -> sign(id).getString("absent")
        null -> sign(id).getString("name")
    }

    val notSure: String get() = t.getJSONObject("answers").getString("not_sure")
}

package org.tinyclinic.app.engine

/**
 * What the health worker should do (port of engine/decide.py; same rules, same test vectors).
 *
 * Referral is never delayed: a present sign refers at once, whatever else is unknown.
 * "No danger sign" needs every sign, and the age, settled: answered by the health worker,
 * or read from the note with confidence at or above the rule pack's threshold.
 */
enum class Outcome { REFER_URGENT, NEED_INFO, UNSURE, NO_DANGER_SIGN }

/** The health worker has not answered this slot. */
object NotAsked

class Observation(
    var model: Any? = null,        // value read from the note; null = not mentioned
    var confidence: Double? = null, // the model's confidence in that value
    var worker: Any? = NotAsked,   // the health worker's answer; null = "not sure"
) {
    val asked get() = worker !== NotAsked
    val value: Any? get() = if (asked) worker else model
}

class Case(val obs: MutableMap<String, Observation>) {

    fun answer(slot: String, value: Any?): Case {
        obs.getValue(slot).worker = when (value) {
            "present" -> true
            "absent" -> false
            "not_sure" -> null
            else -> value
        }
        return this
    }

    fun values(): Map<String, Any?> = obs.mapValues { it.value.value }

    companion object {
        const val AGE = "age"
        val DOCUMENTATION = listOf("sex", "complaints", "duration", "temperature")

        fun empty(rules: Rules) =
            Case((listOf(AGE) + DOCUMENTATION + rules.signIds).associateWith { Observation() }.toMutableMap())

        /** From the model's record; an unreadable record gives an empty case, so every question is asked. */
        fun fromRecord(line: String, rules: Rules, confidence: (String) -> Double? = { null }): Case {
            val case = empty(rules)
            val values = try {
                Record.parse(line, rules)
            } catch (e: IllegalArgumentException) {
                return case
            }
            for ((slot, value) in values) case.obs[slot] = Observation(model = value, confidence = confidence(slot))
            return case
        }
    }
}

data class Decision(
    val outcome: Outcome,
    val present: List<String> = emptyList(),   // danger signs found
    val questions: List<String> = emptyList(), // slots to ask next, in protocol order
    val pending: List<String> = emptyList(),   // signs still unchecked when referring; never wait for them
    val reasons: List<Pair<String, Map<String, Any>>> = emptyList(),
    val warnings: List<Pair<String, Map<String, Any>>> = emptyList(),
    val cite: String = "",
)

// "Not sure" from the health worker never cancels a sign the note reads as present.
private fun Observation.present() = value == true || (asked && worker == null && model == true)

private fun Observation.settled(threshold: Double): Boolean =
    if (asked) worker != null else model != null && (confidence ?: return false) >= threshold

fun decide(case: Case, rules: Rules): Decision {
    val obs = case.obs
    val threshold = rules.modelAbsentMinConfidence
    val present = rules.signIds.filter { obs.getValue(it).present() }
    val unresolved = rules.signIds.filter { it !in present && !obs.getValue(it).settled(threshold) }

    val warnings = mutableListOf<Pair<String, Map<String, Any>>>()
    val overridden = rules.signIds.filter {
        val o = obs.getValue(it)
        o.asked && o.model != null && o.worker != null && o.worker != o.model
    }
    if (overridden.isNotEmpty()) warnings += "overridden" to mapOf("signs" to overridden)
    for (rule in rules.consistency) {
        if (obs.getValue(rule.ifPresent).present() && obs.getValue(rule.expectPresent).value == false) {
            warnings += rule.warning to emptyMap()
        }
    }
    val temperature = obs.getValue("temperature").value as Double?
    if (temperature != null && temperature !in rules.temperaturePlausible) {
        warnings += "temperature_implausible" to mapOf("value" to temperature)
    }

    if (present.isNotEmpty()) {
        return Decision(Outcome.REFER_URGENT, present = present, pending = unresolved, warnings = warnings, cite = rules.cite)
    }

    val age = obs.getValue(Case.AGE)
    val questions = (if (!age.asked && !age.settled(threshold)) listOf(Case.AGE) else emptyList()) +
        unresolved.filter { !obs.getValue(it).asked }
    if (questions.isNotEmpty()) return Decision(Outcome.NEED_INFO, questions = questions, warnings = warnings)

    val reasons = mutableListOf<Pair<String, Map<String, Any>>>()
    if (unresolved.isNotEmpty()) reasons += "not_checked" to mapOf("signs" to unresolved)
    val months = age.value as Int?
    when {
        months == null -> reasons += "age_unknown" to emptyMap()
        months !in rules.minAgeMonths..rules.maxAgeMonths -> reasons += "age_out_of_scope" to emptyMap()
    }
    if (reasons.isNotEmpty()) return Decision(Outcome.UNSURE, reasons = reasons, warnings = warnings)
    return Decision(Outcome.NO_DANGER_SIGN, warnings = warnings)
}

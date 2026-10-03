package org.tinyclinic.app.engine

import java.util.Locale

/**
 * The compact case record (port of engine/record.py):
 *
 *     A24 F | C:FEV,CGH D2 T38.9 | DRK0 VOM1 CNV? LTH0 CNN0
 *
 * Values: age in months, sex, complaints, days ill, temperature, then one value per danger
 * sign (1 present, 0 absent, ? unknown). Unknown values are null.
 */
object Record {
    private const val NUMBER = "(?:[0-9]|[1-9][0-9])"
    private const val TEMPERATURE = "[34][0-9]\\.[0-9]"

    /** Java named groups allow letters and digits only, so signs use their codes. */
    fun pattern(rules: Rules): Regex {
        val code = rules.complaints.joinToString("|", "(?:", ")") { Regex.escape(it) }
        val complaints = "\\?|$code(?:,$code){0,${rules.maxComplaints - 1}}"
        val signs = rules.signs.joinToString(" ") { "${it.code}(?<${it.code}>[01?])" }
        return Regex(
            "A(?<age>$NUMBER|\\?) (?<sex>[MF?]) \\| C:(?<complaints>$complaints) " +
                "D(?<duration>$NUMBER|\\?) T(?<temperature>$TEMPERATURE|\\?) \\| $signs"
        )
    }

    /** Record line to {slot: value}; throws IllegalArgumentException if the line is not a record. */
    fun parse(line: String, rules: Rules): Map<String, Any?> {
        val match = pattern(rules).matchEntire(line.trim())
            ?: throw IllegalArgumentException("not a case record: $line")
        fun group(name: String) = match.groups[name]!!.value.takeUnless { it == "?" }
        val values = mutableMapOf<String, Any?>(
            "age" to group("age")?.toInt(),
            "sex" to group("sex"),
            "complaints" to group("complaints")?.split(","),
            "duration" to group("duration")?.toInt(),
            "temperature" to group("temperature")?.toDouble(),
        )
        for (sign in rules.signs) {
            values[sign.id] = when (match.groups[sign.code]!!.value) {
                "1" -> true
                "0" -> false
                else -> null
            }
        }
        return values
    }

    fun format(values: Map<String, Any?>, rules: Rules): String {
        fun number(value: Any?) = (value as Int?)?.also { require(it in 0..99) { "$it does not fit" } }?.toString() ?: "?"
        val temperature = values["temperature"] as Double?
        require(temperature == null || temperature in 30.0..49.9) { "temperature $temperature does not fit" }
        @Suppress("UNCHECKED_CAST")
        val complaints = (values["complaints"] as List<String>?).orEmpty()
        require(complaints.size <= rules.maxComplaints && complaints.all { it in rules.complaints })
        val signs = rules.signs.joinToString(" ") { sign ->
            sign.code + when (values[sign.id]) {
                true -> "1"
                false -> "0"
                else -> "?"
            }
        }
        val temperatureText = temperature?.let { String.format(Locale.ROOT, "%.1f", it) } ?: "?"
        return "A${number(values["age"])} ${values["sex"] ?: "?"} | C:${complaints.joinToString(",").ifEmpty { "?" }} " +
            "D${number(values["duration"])} T$temperatureText | $signs"
    }
}

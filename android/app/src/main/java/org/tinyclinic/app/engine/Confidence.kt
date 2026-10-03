package org.tinyclinic.app.engine

import org.tinyclinic.llama.LlamaEngine

/**
 * Per-slot confidence from the model's token probabilities.
 *
 * The grammar forces the record's fixed parts ("A", " | C:", " DRK"...), so those tokens have
 * probability 1; the real choices are the values. A slot's confidence is the lowest probability
 * among the tokens that wrote its value.
 */
object Confidence {

    fun perSlot(record: String, pieces: List<LlamaEngine.Piece>, rules: Rules): Map<String, Double> {
        val match = Record.pattern(rules).matchEntire(record) ?: return emptyMap()
        // Character span covered by each token.
        val spans = mutableListOf<Pair<IntRange, Double>>()
        var start = 0
        for (piece in pieces) {
            val end = start + piece.text.length
            if (end > start) spans += (start until end) to piece.probability.toDouble()
            start = end
        }
        fun lowest(range: IntRange): Double? =
            spans.filter { (span, _) -> span.first <= range.last && range.first <= span.last }.minOfOrNull { it.second }

        val groups = mapOf("age" to "age", "sex" to "sex", "complaints" to "complaints",
            "duration" to "duration", "temperature" to "temperature") +
            rules.signs.associate { it.id to it.code }
        return groups.mapNotNull { (slot, group) ->
            match.groups[group]?.range?.let { range -> lowest(range)?.let { slot to it } }
        }.toMap()
    }
}

package org.tinyclinic.app.engine

import android.content.Context
import org.json.JSONObject

/**
 * The rule pack, templates, grammar and prompt, bundled from rules/ by `python -m engine export`.
 * Same source as the Python engine, so both decide the same way.
 */
class Rules(json: JSONObject) {
    private val pack = json.getJSONObject("pack")

    val id: String = pack.getString("id")
    val version: String = pack.getString("version")
    val cite: String = pack.getJSONObject("classification").getString("cite")
    val minAgeMonths: Int = pack.getJSONObject("scope").getInt("min_age_months")
    val maxAgeMonths: Int = pack.getJSONObject("scope").getInt("max_age_months")
    val modelAbsentMinConfidence: Double = pack.getJSONObject("policy").getDouble("model_absent_min_confidence")

    val signs: List<DangerSign> = pack.getJSONArray("danger_signs").let { array ->
        List(array.length()) { i ->
            val s = array.getJSONObject(i)
            DangerSign(s.getString("id"), s.getString("code"), s.getString("check"))
        }
    }
    val signIds: List<String> = signs.map { it.id }

    val consistency: List<Consistency> = pack.optJSONArray("consistency")?.let { array ->
        List(array.length()) { i ->
            val c = array.getJSONObject(i)
            Consistency(c.getString("if_present"), c.getString("expect_present"), c.getString("warning"))
        }
    } ?: emptyList()

    private val record = pack.getJSONObject("record")
    val complaints: List<String> = record.getJSONObject("complaints").keys().asSequence().toList()
    val maxComplaints: Int = record.getInt("max_complaints")
    val temperaturePlausible: ClosedFloatingPointRange<Double> = record.getJSONArray("temperature_plausible_c")
        .let { it.getDouble(0)..it.getDouble(1) }

    val templates: Map<String, JSONObject> = json.getJSONObject("templates").let { all ->
        all.keys().asSequence().associateWith { all.getJSONObject(it) }
    }
    val grammar: String = json.getString("grammar")
    val systemPrompt: String = json.getJSONObject("prompt").getString("system")
    val userPrefix: String = json.getJSONObject("prompt").getString("user_prefix")

    companion object {
        const val ASSET = "tinyclinic_rules.json"

        fun load(context: Context): Rules =
            Rules(JSONObject(context.assets.open(ASSET).bufferedReader().use { it.readText() }))
    }
}

data class DangerSign(val id: String, val code: String, val check: String)

data class Consistency(val ifPresent: String, val expectPresent: String, val warning: String)

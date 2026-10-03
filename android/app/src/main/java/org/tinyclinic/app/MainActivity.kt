package org.tinyclinic.app

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.safeDrawingPadding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.FilterChip
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.darkColorScheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.viewmodel.compose.viewModel
import org.tinyclinic.app.AppViewModel.Step
import org.tinyclinic.app.engine.Messages
import org.tinyclinic.app.engine.Outcome

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        setContent {
            MaterialTheme(colorScheme = if (isSystemInDarkTheme()) darkColorScheme() else lightColorScheme()) {
                Surface(modifier = Modifier.fillMaxSize()) { TinyClinicApp() }
            }
        }
    }
}

@OptIn(ExperimentalLayoutApi::class)
@Composable
fun TinyClinicApp(vm: AppViewModel = viewModel()) {
    val state by vm.state.collectAsStateWithLifecycle()
    Column(
        modifier = Modifier
            .fillMaxSize()
            .safeDrawingPadding()
            .verticalScroll(rememberScrollState())
            .padding(20.dp),
        verticalArrangement = Arrangement.spacedBy(16.dp),
    ) {
        Text("Tiny Clinic", style = MaterialTheme.typography.headlineMedium, fontWeight = FontWeight.SemiBold)
        FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            vm.languages.forEach { lang ->
                FilterChip(
                    selected = state.language == lang.language,
                    onClick = { vm.setLanguage(lang.language) },
                    label = { Text(lang.name + if (lang.isDraft) " (draft)" else "") },
                )
            }
        }
        when (state.step) {
            Step.NOTE -> NoteStep(state, vm)
            Step.READING -> Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                CircularProgressIndicator(modifier = Modifier.size(28.dp))
                Text("Reading the note on the phone…")
            }
            Step.QUESTION -> state.question?.let { QuestionStep(it, vm) }
            Step.RESULT -> ResultStep(state, vm)
        }
    }
}

@Composable
private fun NoteStep(state: AppViewModel.UiState, vm: AppViewModel) {
    OutlinedTextField(
        value = state.note,
        onValueChange = vm::setNote,
        modifier = Modifier.fillMaxWidth().heightIn(min = 140.dp),
        label = { Text("What do you see? Any language.") },
    )
    Button(onClick = vm::check, modifier = Modifier.fillMaxWidth().heightIn(min = 52.dp)) {
        Text(if (state.modelReady) "Check" else "Check (no model: ask every question)")
    }
    InfoCard("Status", state.status)
    InfoCard(
        "On-device engine",
        if (state.engineReady) "llama.cpp · CPU: ${state.cpuFeatures.joinToString(", ")}" else "Starting…",
    )
    InfoCard("Model", state.modelDescription?.let { "${state.modelName}\n$it" } ?: (state.modelName ?: "None"))
    InfoCard("Model folder", state.modelFolder, monospace = true)
}

@Composable
private fun QuestionStep(question: Messages.Question, vm: AppViewModel) {
    Text(question.text, style = MaterialTheme.typography.titleLarge)
    when (question.kind) {
        Messages.Question.Kind.MONTHS -> {
            var months by remember(question.slot) { mutableStateOf("") }
            OutlinedTextField(
                value = months,
                onValueChange = { months = it.filter(Char::isDigit).take(2) },
                keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number),
                label = { Text("months") },
                singleLine = true,
                modifier = Modifier.fillMaxWidth(),
            )
            Button(onClick = { vm.answer(months.toIntOrNull()) }, enabled = months.isNotEmpty(),
                modifier = Modifier.fillMaxWidth().heightIn(min = 52.dp)) { Text("OK") }
            question.options.forEach { option ->
                OutlinedButton(onClick = { vm.answer(option.value) }, modifier = Modifier.fillMaxWidth()) { Text(option.label) }
            }
        }
        Messages.Question.Kind.CHOICE -> question.options.forEach { option ->
            OutlinedButton(onClick = { vm.answer(option.value) }, modifier = Modifier.fillMaxWidth().heightIn(min = 56.dp)) {
                Text(option.label, style = MaterialTheme.typography.titleMedium)
            }
        }
    }
}

@Composable
private fun ResultStep(state: AppViewModel.UiState, vm: AppViewModel) {
    val result = state.result ?: return
    val (container, content) = when (result.outcome) {
        Outcome.REFER_URGENT -> Color(0xFFB3261E) to Color.White
        Outcome.NO_DANGER_SIGN -> Color(0xFF1E6B35) to Color.White
        else -> Color(0xFFFFD27A) to Color(0xFF3A2A00)
    }
    Card(colors = CardDefaults.cardColors(containerColor = container, contentColor = content), modifier = Modifier.fillMaxWidth()) {
        Text(result.text, modifier = Modifier.padding(20.dp), style = MaterialTheme.typography.titleLarge, fontWeight = FontWeight.SemiBold)
    }
    result.warnings.forEach { InfoCard("Check", it) }
    Card(modifier = Modifier.fillMaxWidth()) {
        Column(modifier = Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
            Text("Danger signs", style = MaterialTheme.typography.titleSmall, color = MaterialTheme.colorScheme.primary)
            state.signs.forEach { line ->
                Row(verticalAlignment = Alignment.CenterVertically, modifier = Modifier.fillMaxWidth()) {
                    Column(modifier = Modifier.weight(1f)) {
                        Text(line.text, fontWeight = if (line.present) FontWeight.Bold else FontWeight.Normal,
                            color = if (line.present) Color(0xFFB3261E) else MaterialTheme.colorScheme.onSurface)
                        Text(line.source, style = MaterialTheme.typography.bodySmall,
                            color = MaterialTheme.colorScheme.onSurfaceVariant)
                    }
                    TextButton(onClick = { vm.change(line.id) }) { Text("Change") }
                }
            }
        }
    }
    InfoCard("Record", state.record + (state.reading?.extraction?.let {
        "\n${it.promptTokens} prompt tokens (${it.reusedTokens} cached), ${it.generatedTokens} written, " +
            "${it.promptMs + it.generateMs} ms"
    } ?: ""), monospace = true)
    state.decision?.cite?.takeIf { it.isNotEmpty() }?.let { InfoCard("Source", it) }
    Button(onClick = vm::newCheck, modifier = Modifier.fillMaxWidth().heightIn(min = 52.dp)) { Text("New check") }
}

@Composable
private fun InfoCard(title: String, body: String, monospace: Boolean = false) {
    Card(modifier = Modifier.fillMaxWidth()) {
        Column(modifier = Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
            Text(title, style = MaterialTheme.typography.titleSmall, color = MaterialTheme.colorScheme.primary)
            Text(body, style = MaterialTheme.typography.bodyMedium,
                fontFamily = if (monospace) FontFamily.Monospace else FontFamily.Default)
        }
    }
}

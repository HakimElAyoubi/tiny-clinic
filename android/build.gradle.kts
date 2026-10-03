plugins {
    alias(libs.plugins.android.application) apply false
    alias(libs.plugins.android.library) apply false
    // AGP 9 compiles Kotlin itself; declaring KGP here only lifts it to the catalog version,
    // which the Compose compiler plugin must match.
    alias(libs.plugins.kotlin.android) apply false
    alias(libs.plugins.kotlin.compose) apply false
}

// The repo sits in an iCloud-synced folder. iCloud skips names ending in .nosync, so build
// outputs stay local: synced build files get "Foo 2.class" conflict copies that break dexing.
allprojects {
    layout.buildDirectory = layout.projectDirectory.dir("build.nosync")
}

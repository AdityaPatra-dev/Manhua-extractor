plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
    id("com.chaquo.python")
}

android {
    namespace = "com.manhua.extractor"
    compileSdk = 34

    defaultConfig {
        applicationId = "com.manhua.extractor"
        minSdk = 26
        targetSdk = 34
        versionCode = 12
        versionName = "1.2.1"

        testInstrumentationRunner = "androidx.test.runner.AndroidJUnitRunner"

        ndk {
            abiFilters.addAll(listOf("arm64-v8a", "armeabi-v7a", "x86_64"))
        }

        chaquopy {
            defaultConfig {
                version = "3.11"
                pip {
                    install("pydantic==1.10.18")
                    install("fastapi==0.99.1")
                    install("python-multipart")
                    install("h11==0.14.0")
                    install("uvicorn==0.22.0")
                    install("requests==2.32.3")
                    install("httpx==0.24.1")
                    install("beautifulsoup4==4.12.3")
                    install("pillow")
                    install("aiohttp")
                }
            }
        }
    }

    signingConfigs {
        create("release") {
            storeFile = file("release.keystore")
            storePassword = "manhuaextractor"
            keyAlias = "manhua-extractor"
            keyPassword = "manhuaextractor"
        }
    }

    buildTypes {
        release {
            isMinifyEnabled = false
            signingConfig = signingConfigs.getByName("release")
            proguardFiles(
                getDefaultProguardFile("proguard-android-optimize.txt"),
                "proguard-rules.pro"
            )
        }
        debug {
            isMinifyEnabled = false
            signingConfig = signingConfigs.getByName("release")
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    kotlinOptions {
        jvmTarget = "17"
    }

    buildFeatures {
        viewBinding = true
    }

    packaging {
        jniLibs {
            useLegacyPackaging = true
        }
    }
}

val copyPythonSources = tasks.register<Copy>("copyPythonSources") {
    outputs.upToDateWhen { false }
    from("${rootProject.projectDir}/..") {
        include("app.py")
        include("android_entry.py")
        include("manhua.py")
        include("core/**")
        include("extractors/**")
        include("database/**")
        include("static/**")
    }
    into("${projectDir}/src/main/python")
}

tasks.matching { it.name.contains("Python") && it.name != "copyPythonSources" }.configureEach {
    dependsOn(copyPythonSources)
}

tasks.named("preBuild") {
    dependsOn(copyPythonSources)
}

dependencies {
    implementation("androidx.core:core-ktx:1.13.1")
    implementation("androidx.appcompat:appcompat:1.7.0")
    implementation("com.google.android.material:material:1.12.0")
    implementation("androidx.constraintlayout:constraintlayout:2.1.4")
    implementation("androidx.webkit:webkit:1.11.0")
}


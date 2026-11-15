import os

FILES = {
    "settings.gradle": """rootProject.name = 'BumpNavNoRoot'
include ':app'
""",
    "build.gradle": """buildscript {
    repositories {
        google()
        mavenCentral()
    }
    dependencies {
        classpath 'com.android.tools.build:gradle:8.1.2'
    }
}
allprojects {
    repositories {
        google()
        mavenCentral()
    }
}
""",
    "app/build.gradle": """plugins {
    id 'com.android.application'
}
android {
    namespace 'com.t4.bumploc'
    compileSdk 34

    defaultConfig {
        applicationId "com.t4.bumploc"
        minSdk 26
        targetSdk 34
        versionCode 2
        versionName "2.0-noroot"
    }
    compileOptions {
        sourceCompatibility JavaVersion.VERSION_11
        targetCompatibility JavaVersion.VERSION_11
    }
}
dependencies {
}
""",
    "app/src/main/AndroidManifest.xml": """<?xml version="1.0" encoding="utf-8"?>
<manifest xmlns:android="http://schemas.android.com/apk/res/android"
    xmlns:tools="http://schemas.android.com/tools">

    <uses-permission android:name="android.permission.SYSTEM_ALERT_WINDOW" />
    <uses-permission android:name="android.permission.FOREGROUND_SERVICE" />
    <uses-permission android:name="android.permission.ACCESS_FINE_LOCATION" />
    <uses-permission android:name="android.permission.ACCESS_COARSE_LOCATION" />
    <uses-permission android:name="android.permission.ACCESS_MOCK_LOCATION"
        tools:ignore="MockLocation,ProtectedPermissions" />

    <application
        android:label="T4 Bump Nav"
        android:theme="@android:style/Theme.DeviceDefault.NoActionBar">
        <activity
            android:name=".MainActivity"
            android:exported="true">
            <intent-filter>
                <action android:name="android.intent.action.MAIN" />
                <category android:name="android.intent.category.LAUNCHER" />
            </intent-filter>
        </activity>
        <service
            android:name=".OverlayService"
            android:enabled="true"
            android:exported="false" />
    </application>
</manifest>
""",
    "app/src/main/java/com/t4/bumploc/MainActivity.java": r"""package com.t4.bumploc;

import android.app.Activity;
import android.content.Intent;
import android.net.Uri;
import android.os.Bundle;
import android.provider.Settings;
import android.view.Gravity;
import android.widget.Button;
import android.widget.LinearLayout;
import android.widget.TextView;
import android.graphics.Color;

public class MainActivity extends Activity {
    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);

        LinearLayout layout = new LinearLayout(this);
        layout.setOrientation(LinearLayout.VERTICAL);
        layout.setGravity(Gravity.CENTER);
        layout.setBackgroundColor(Color.rgb(16, 16, 22));
        layout.setPadding(48, 48, 48, 48);

        TextView info = new TextView(this);
        info.setText("T4 // BUMP EXTERNAL OVERLAY (NO ROOT)\n\n" +
                     "1. Выдай разрешение 'Поверх других окон'\n" +
                     "2. В 'Параметрах разработчика' выбери Т4 Bump Nav в пункте 'Приложение для фиктивных местоположений'\n" +
                     "3. Нажми 'Запустить оверлей' и открой Bump");
        info.setTextColor(Color.rgb(235, 235, 245));
        info.setTextSize(14f);
        layout.addView(info);

        Button btnPerm = new Button(this);
        btnPerm.setText("1. Разрешить окно поверх других");
        btnPerm.setOnClickListener(v -> {
            if (!Settings.canDrawOverlays(this)) {
                Intent intent = new Intent(Settings.ACTION_MANAGE_OVERLAY_PERMISSION,
                        Uri.parse("package:" + getPackageName()));
                startActivity(intent);
            }
        });
        layout.addView(btnPerm);

        Button btnDev = new Button(this);
        btnDev.setText("2. Открыть Параметры разработчика");
        btnDev.setOnClickListener(v -> {
            try {
                startActivity(new Intent(Settings.ACTION_APPLICATION_DEVELOPMENT_SETTINGS));
            } catch (Exception ignored) {}
        });
        layout.addView(btnDev);

        Button btnStart = new Button(this);
        btnStart.setText("3. Запустить оверлей T4");
        btnStart.setOnClickListener(v -> {
            if (Settings.canDrawOverlays(this)) {
                startService(new Intent(this, OverlayService.class));
                finish();
            } else {
                Intent intent = new Intent(Settings.ACTION_MANAGE_OVERLAY_PERMISSION,
                        Uri.parse("package:" + getPackageName()));
                startActivity(intent);
            }
        });
        layout.addView(

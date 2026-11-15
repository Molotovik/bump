import os

# Структура файлов проекта
FILES = {
    "settings.gradle": """rootProject.name = 'BumpNav'
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
        maven { url 'https://api.xposed.info/' }
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
        versionCode 1
        versionName "1.0"
    }
    compileOptions {
        sourceCompatibility JavaVersion.VERSION_11
        targetCompatibility JavaVersion.VERSION_11
    }
}
dependencies {
    compileOnly 'de.robv.android.xposed:api:82'
}
""",
    "app/src/main/AndroidManifest.xml": """<?xml version="1.0" encoding="utf-8"?>
<manifest xmlns:android="http://schemas.android.com/apk/res/android">
    <application android:label="T4 Bump Nav">
        <meta-data android:name="xposedmodule" android:value="true" />
        <meta-data android:name="xposeddescription" android:value="T4 Location &amp; Fog Unlocker for Bump" />
        <meta-data android:name="xposedminversion" android:value="82" />
        <meta-data android:name="xposedscope" android:value="com.bump.app;app.bump;com.Zenly.Bump" />
    </application>
</manifest>
""",
    "app/src/main/assets/xposed_init": """com.t4.bumploc.BumpHook
""",
    "app/src/main/java/com/t4/bumploc/BumpHook.java": r"""package com.t4.bumploc;

import android.app.Activity;
import android.content.Context;
import android.graphics.Color;
import android.graphics.PixelFormat;
import android.graphics.drawable.GradientDrawable;
import android.location.Location;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.view.Gravity;
import android.view.MotionEvent;
import android.view.View;
import android.view.WindowManager;
import android.widget.Button;
import android.widget.LinearLayout;
import android.widget.TextView;

import org.json.JSONObject;

import java.io.File;
import java.io.FileInputStream;
import java.io.FileOutputStream;
import java.nio.charset.StandardCharsets;
import java.util.HashSet;
import java.util.Set;

import de.robv.android.xposed.IXposedHookLoadPackage;
import de.robv.android.xposed.XC_MethodHook;
import de.robv.android.xposed.XC_MethodReplacement;
import de.robv.android.xposed.XposedBridge;
import de.robv.android.xposed.XposedHelpers;
import de.robv.android.xposed.callbacks.XC_LoadPackage;

// BUILD ID: T4-BUMP-CLOUD-02
// PROJECTION CONVENTION: Geographic Spherical (WGS84 Lat/Lon) -> Equirectangular local step, behind-camera N/A (2D surface), clamp [-89.99..89.99, -180..180]
public class BumpHook implements IXposedHookLoadPackage {

    // --- CONFIGURATION & OFFSETS BLOCK ---
    // DERIVE: pm list packages | grep -i bump
    private static final String CONFIG_FILE_NAME = "t4_bump_config.json";
    private static final int COLOR_BG = Color.argb(225, 16, 16, 22);
    private static final int COLOR_ACCENT = Color.argb(255, 56, 152, 255);
    private static final int COLOR_TEXT = Color.argb(255, 240, 240, 250);
    private static final int COLOR_ACTIVE = Color.argb(255, 50, 215, 75);
    private static final float FONT_SIZE = 11.5f;
    private static final long UPDATE_INTERVAL_MS = 1000L;

    // Runtime state (no spoofing active on launch without explicit toggle)
    private static volatile boolean isSpoofEnabled = false;
    private static volatile boolean isAutoWalkEnabled = false;
    private static volatile double currentLat = 52.2297; // Warsaw
    private static volatile double currentLon = 21.0122;
    private static volatile double walkStepDegrees = 0.00030;
    private static volatile double walkAngleRad = 0.0;

    private final Set<XC_MethodHook.Unhook> activeHooks = new HashSet<>();
    private WindowManager windowManager = null;
    private View overlayRoot = null;
    private Handler walkHandler = null;
    private File configFile = null;

    @Override
    public void handleLoadPackage(final XC_LoadPackage.LoadPackageParam lpparam) throws Throwable {
        if (lpparam.packageName.equals("android") || lpparam.packageName.equals("com.t4.bumploc")) {
            return;
        }
        installLocationHooks();
        installLifecycleHook();
    }

    private void installLocationHooks() {
        try {
            activeHooks.add(XposedHelpers.findAndHookMethod(
                Location.class, "getLatitude", new XC_MethodHook() {
                    @Override
                    protected void afterHookedMethod(MethodHookParam param) {
                        if (isSpoofEnabled) param.setResult(clampLat(currentLat));
                    }
                }
            ));

            activeHooks.add(XposedHelpers.findAndHookMethod(
                Location.class, "getLongitude", new XC_MethodHook() {
                    @Override
                    protected void afterHookedMethod(MethodHookParam param) {
                        if (isSpoofEnabled) param.setResult(clampLon(currentLon));
                    }
                }
            ));

            activeHooks.add(XposedHelpers.findAndHookMethod(
                Location.class, "isFromMockProvider", XC_MethodReplacement.returnConstant(false)
            ));

            try {
                activeHooks.add(XposedHelpers.findAndHookMethod(
                    Location.class, "isMock", XC_MethodReplacement.returnConstant(false)
                ));
            } catch (Throwable ignored) {}
        } catch (Throwable t) {
            XposedBridge.log("T4 Hook Error: " + t.getMessage());
        }
    }

    private void installLifecycleHook() {
        activeHooks.add(XposedHelpers.findAndHookMethod(
            Activity.class, "onResume", new XC_MethodHook() {
                @Override
                protected void afterHookedMethod(MethodHookParam param) {
                    final Activity activity = (Activity) param.thisObject;
                    if (configFile == null) {
                        configFile = new File(activity.getFilesDir(), CONFIG_FILE_NAME);
                        loadConfig();
                    }
                    new Handler(Looper.getMainLooper()).postDelayed(() -> {
                        if (!activity.isFinishing() && overlayRoot == null) {
                            buildOverlay(activity);
                        }
                    }, 800);
                }
            }
        ));
    }

    private static double clampLat(double lat) {
        return Math.max(-89.9999, Math.min(89.9999, lat));
    }

    private static double clampLon(double lon) {
        if (lon > 180.0) return lon - 360.0;
        if (lon < -180.0) return lon + 360.0;
        return lon;
    }

    private void buildOverlay(final Activity context) {
        windowManager = (WindowManager) context.getSystemService(Context.WINDOW_SERVICE);
        if (windowManager == null) return;

        final WindowManager.LayoutParams params = new WindowManager.LayoutParams(
            WindowManager.LayoutParams.WRAP_CONTENT,
            WindowManager.LayoutParams.WRAP_CONTENT,
            WindowManager.LayoutParams.TYPE_APPLICATION_PANEL,
            WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE,
            PixelFormat.TRANSLUCENT
        );
        params.gravity = Gravity.TOP | Gravity.START;
        params.x = 50;
        params.y = 160;

        LinearLayout root = new LinearLayout(context);
        root.setOrientation(LinearLayout.VERTICAL);
        root.setPadding(24, 18, 24, 18);
        GradientDrawable bg = new GradientDrawable();
        bg.setColor(COLOR_BG);
        bg.setCornerRadius(18f);
        bg.setStroke(2, COLOR_ACCENT);
        root.setBackground(bg);

        TextView header = new TextView(context);
        header.setText("T4 // BUMP OVERLAY (Зажми для переноса)");
        header.setTextColor(COLOR_ACCENT);
        header.setTextSize(FONT_SIZE);
        root.addView(header);

        final TextView statusText = new TextView(context);
        statusText.setTextColor(COLOR_TEXT);
        statusText.setTextSize(FONT_SIZE - 1);
        updateStatusLabel(statusText);
        root.addView(statusText);

        LinearLayout tabRow = new LinearLayout(context);
        tabRow.setOrientation(LinearLayout.HORIZONTAL);
        Button btnTabVis = makeButton(context, "Города");
        Button btnTabProj = makeButton(context, "Туман");
        Button btnTabCfg = makeButton(context, "Опции");
        tabRow.addView(btnTabVis);
        tabRow.addView(btnTabProj);
        tabRow.addView(btnTabCfg);
        root.addView(tabRow);

        final LinearLayout tabVis = new LinearLayout(context);
        tabVis.setOrientation(LinearLayout.VERTICAL);

        final LinearLayout tabProj = new LinearLayout(context);
        tabProj.setOrientation(LinearLayout.VERTICAL);
        tabProj.setVisibility(View.GONE);

        final LinearLayout tabCfg = new LinearLayout(context);
        tabCfg.setOrientation(LinearLayout.VERTICAL);
        tabCfg.setVisibility(View.GONE);

        // --- TAB 1: CITIES ---
        final Button btnToggle = makeButton(context, "Спуфинг: ВЫКЛ");
        btnToggle.setOnClickListener(v -> {
            isSpoofEnabled = !isSpoofEnabled;
            btnToggle.setText(isSpoofEnabled ? "Спуфинг: ВКЛ" : "Спуфинг: ВЫКЛ");
            btnToggle.setTextColor(isSpoofEnabled ? COLOR_ACTIVE : COLOR_TEXT);
            updateStatusLabel(statusText);
        });
        tabVis.addView(btnToggle);

        addCity(context, tabVis, "Варшава", 52.2297, 21.0122, statusText);
        addCity(context, tabVis, "Торунь", 53.0138, 18.5984, statusText);
        addCity(context, tabVis, "Токио", 35.6762, 139.6503, statusText);
        addCity(context, tabVis, "Нью-Йорк", 40.7128, -74.0060, statusText);
        addCity(context, tabVis, "Париж", 48.8566, 2.3522, statusText);
        addCity(context, tabVis, "Лондон", 51.5074, -0.1278, statusText);

        // --- TAB 2: FOG UNLOCKER & JOYSTICK ---
        final Button btnWalk = makeButton(context, "Авто-открытие карты: ВЫКЛ");
        btnWalk.setOnClickListener(v -> {
            isAutoWalkEnabled = !isAutoWalkEnabled;
            btnWalk.setText(isAutoWalkEnabled ? "Авто-открытие: ВКЛ" : "Авто-открытие: ВЫКЛ");
            btnWalk.setTextColor(isAutoWalkEnabled ? COLOR_ACTIVE : COLOR_TEXT);
        });
        tabProj.addView(btnWalk);

        LinearLayout dpad = new LinearLayout(context);
        dpad.setOrientation(LinearLayout.HORIZONTAL);
        Button bN = makeButton(context, "⬆️");
        Button bS = makeButton(context, "⬇️");
        Button bW = makeButton(context, "⬅️");
        Button bE = makeButton(context, "➡️");
        bN.setOnClickListener(v -> { currentLat = clampLat(currentLat + walkStepDegrees * 3); updateStatusLabel(statusText); });
        bS.setOnClickListener(v -> { currentLat = clampLat(currentLat - walkStepDegrees * 3); updateStatusLabel(statusText); });
        bW.setOnClickListener(v -> { currentLon = clampLon(currentLon - walkStepDegrees * 3); updateStatusLabel(statusText); });
        bE.setOnClickListener(v -> { currentLon = clampLon(currentLon + walkStepDegrees * 3); updateStatusLabel(statusText); });
        dpad.addView(bN); dpad.addView(bS); dpad.addView(bW); dpad.addView(bE);
        tabProj.addView(dpad);

        // --- TAB 3: CONFIG & UNLOAD ---
        Button btnSave = makeButton(context, "Сохранить точку в JSON");
        btnSave.setOnClickListener(v -> saveConfig());
        Button btnUnload = makeButton(context, "Выгрузить хук и закрыть");
        btnUnload.setOnClickListener(v -> cleanupAndRestore());
        tabCfg.addView(btnSave);
        tabCfg.addView(btnUnload);

        root.addView(tabVis);
        root.addView(tabProj);
        root.addView(tabCfg);

        btnTabVis.setOnClickListener(v -> { tabVis.setVisibility(View.VISIBLE); tabProj.setVisibility(View.GONE); tabCfg.setVisibility(View.GONE); });
        btnTabProj.setOnClickListener(v -> { tabVis.setVisibility(View.GONE); tabProj.setVisibility(View.VISIBLE); tabCfg.setVisibility(View.GONE); });
        btnTabCfg.setOnClickListener(v -> { tabVis.setVisibility(View.GONE); tabProj.setVisibility(View.GONE); tabCfg.setVisibility(View.VISIBLE); });

        header.setOnTouchListener(new View.OnTouchListener() {
            private int initX, initY;
            private float touchX, touchY;
            @Override
            public boolean onTouch(View v, MotionEvent event) {
                if (event.getAction() == MotionEvent.ACTION_DOWN) {
                    initX = params.x; initY = params.y;
                    touchX = event.getRawX(); touchY = event.getRawY();
                    return true;
                } else if (event.getAction() == MotionEvent.ACTION_MOVE) {
                    params.x = initX + (int) (event.getRawX() - touchX);
                    params.y = initY + (int) (event.getRawY() - touchY);
                    if (overlayRoot != null && windowManager != null) {
                        windowManager.updateViewLayout(overlayRoot, params);
                    }
                    return true;
                }
                return false;
            }
        });

        overlayRoot = root;
        try {
            windowManager.addView(overlayRoot, params);
        } catch (Throwable ignored) {}

        walkHandler = new Handler(Looper.getMainLooper());
        walkHandler.postDelayed(new Runnable() {
            @Override
            public void run() {
                if (overlayRoot == null) return;
                if (isSpoofEnabled && isAutoWalkEnabled) {
                    walkAngleRad += 0.3;
                    currentLat = clampLat(currentLat + Math.sin(walkAngleRad) * walkStepDegrees);
                    currentLon = clampLon(currentLon + Math.cos(walkAngleRad) * walkStepDegrees);
                    updateStatusLabel(statusText);
                }
                walkHandler.postDelayed(this, UPDATE_INTERVAL_MS);
            }
        }, UPDATE_INTERVAL_MS);
    }

    private void addCity(Context ctx, LinearLayout parent, String name, final double lat, final double lon, final TextView status) {
        Button b = makeButton(ctx, name);
        b.setOnClickListener(v -> {
            currentLat = clampLat(lat);
            currentLon = clampLon(lon);
            updateStatusLabel(status);
        });
        parent.addView(b);
    }

    private Button makeButton(Context ctx, String text) {
        Button b = new Button(ctx);
        b.setText(text);
        b.setTextColor(COLOR_TEXT);
        b.setTextSize(FONT_SIZE - 1);
        b.setAllCaps(false);
        b.setBackgroundColor(Color.argb(140, 42, 42, 54));
        b.setPadding(14, 6, 14, 6);
        return b;
    }

    private void updateStatusLabel(TextView tv) {
        tv.setText(String.format("[%s] %.4f, %.4f", isSpoofEnabled ? "ON" : "OFF", currentLat, currentLon));
    }

    private void saveConfig() {
        if (configFile == null) return;
        try {
            JSONObject obj = new JSONObject();
            obj.put("lat", currentLat);
            obj.put("lon", currentLon);
            FileOutputStream fos = new FileOutputStream(configFile);
            fos.write(obj.toString().getBytes(StandardCharsets.UTF_8));
            fos.close();
        } catch (Exception ignored) {}
    }

    private void loadConfig() {
        if (configFile == null || !configFile.exists()) return;
        try {
            FileInputStream fis = new FileInputStream(configFile);
            byte[] data = new byte[(int) configFile.length()];
            fis.read(data);
            fis.close();
            JSONObject obj = new JSONObject(new String(data, StandardCharsets.UTF_8));
            currentLat = clampLat(obj.optDouble("lat", currentLat));
            currentLon = clampLon(obj.optDouble("lon", currentLon));
        } catch (Exception ignored) {}
    }

    private void cleanupAndRestore() {
        isSpoofEnabled = false;
        isAutoWalkEnabled = false;
        for (XC_MethodHook.Unhook u : activeHooks) {
            try { u.unhook(); } catch (Throwable ignored) {}
        }
        activeHooks.clear();
        if (walkHandler != null) {
            walkHandler.removeCallbacksAndMessages(null);
            walkHandler = null;
        }
        if (windowManager != null && overlayRoot != null) {
            try { windowManager.removeViewImmediate(overlayRoot); } catch (Throwable ignored) {}
            overlayRoot = null;
            windowManager = null;
        }
        currentLat = 0.0;
        currentLon = 0.0;
    }
}
"""
}

for path, content in FILES.items():
    os.makedirs(os.path.dirname(path) if os.path.dirname(path) else ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
print("T4 Project structure generated.")

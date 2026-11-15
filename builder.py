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
        layout.addView(btnStart);

        setContentView(layout);
    }
}
""",
    "app/src/main/java/com/t4/bumploc/OverlayService.java": r"""package com.t4.bumploc;

import android.app.Service;
import android.content.Context;
import android.content.Intent;
import android.graphics.Color;
import android.graphics.PixelFormat;
import android.graphics.drawable.GradientDrawable;
import android.location.Criteria;
import android.location.Location;
import android.location.LocationManager;
import android.location.provider.ProviderProperties;
import android.os.Build;
import android.os.Handler;
import android.os.IBinder;
import android.os.Looper;
import android.os.SystemClock;
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
import java.util.Random;

// BUILD ID: T4-BUMP-EXT-NOROOT-03
// PROJECTION CONVENTION: Geographic Spherical (WGS84 Lat/Lon) -> Equirectangular local step, behind-camera N/A (2D surface), clamp [-89.99..89.99, -180..180]
public class OverlayService extends Service {

    // --- CONFIGURATION BLOCK ---
    private static final String CONFIG_FILE_NAME = "t4_bump_noroot.json";
    private static final int COLOR_BG = Color.argb(225, 16, 16, 22);
    private static final int COLOR_ACCENT = Color.argb(255, 56, 152, 255);
    private static final int COLOR_TEXT = Color.argb(255, 240, 240, 250);
    private static final int COLOR_ACTIVE = Color.argb(255, 50, 215, 75);
    private static final float FONT_SIZE = 11.5f;
    private static final long UPDATE_INTERVAL_MS = 900L;

    // Runtime state (no spoofing active on launch without explicit toggle)
    private volatile boolean isSpoofEnabled = false;
    private volatile boolean isAutoWalkEnabled = false;
    private volatile double currentLat = 52.2297; // Warsaw
    private volatile double currentLon = 21.0122;
    private volatile double walkStepDegrees = 0.00028;
    private volatile double walkAngleRad = 0.0;

    private WindowManager windowManager;
    private View overlayRoot;
    private LocationManager locationManager;
    private Handler loopHandler;
    private File configFile;
    private final Random jitter = new Random();

    @Override
    public IBinder onBind(Intent intent) {
        return null;
    }

    @Override
    public void onCreate() {
        super.onCreate();
        configFile = new File(getFilesDir(), CONFIG_FILE_NAME);
        loadConfig();
        locationManager = (LocationManager) getSystemService(Context.LOCATION_SERVICE);
        buildOverlay();
    }

    private static double clampLat(double lat) {
        return Math.max(-89.9999, Math.min(89.9999, lat));
    }

    private static double clampLon(double lon) {
        if (lon > 180.0) return lon - 360.0;
        if (lon < -180.0) return lon + 360.0;
        return lon;
    }

    private void initTestProviders() {
        String[] providers = new String[]{LocationManager.GPS_PROVIDER, LocationManager.NETWORK_PROVIDER};
        for (String p : providers) {
            try {
                try { locationManager.removeTestProvider(p); } catch (Throwable ignored) {}
                if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
                    locationManager.addTestProvider(p, false, false, false, false, true, true, true,
                            ProviderProperties.POWER_USAGE_LOW, ProviderProperties.ACCURACY_FINE);
                } else {
                    locationManager.addTestProvider(p, false, false, false, false, true, true, true,
                            Criteria.POWER_LOW, Criteria.ACCURACY_FINE);
                }
                locationManager.setTestProviderEnabled(p, true);
            } catch (Throwable ignored) {}
        }
    }

    private void pushMockLocation(TextView statusView) {
        String[] providers = new String[]{LocationManager.GPS_PROVIDER, LocationManager.NETWORK_PROVIDER};
        for (String p : providers) {
            try {
                Location loc = new Location(p);
                double latJitter = (jitter.nextDouble() - 0.5) * 0.000015;
                double lonJitter = (jitter.nextDouble() - 0.5) * 0.000015;
                loc.setLatitude(clampLat(currentLat + latJitter));
                loc.setLongitude(clampLon(currentLon + lonJitter));
                loc.setAltitude(115.0 + jitter.nextDouble() * 2.0);
                loc.setAccuracy(3.2f + jitter.nextFloat() * 1.5f);
                loc.setSpeed(isAutoWalkEnabled ? 1.4f : 0.05f);
                loc.setBearing((float) ((Math.toDegrees(walkAngleRad) + 360) % 360));
                loc.setTime(System.currentTimeMillis());
                loc.setElapsedRealtimeNanos(SystemClock.elapsedRealtimeNanos());
                if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                    loc.setVerticalAccuracyMeters(2.0f);
                    loc.setSpeedAccuracyMetersPerSecond(0.2f);
                    loc.setBearingAccuracyDegrees(5.0f);
                }
                locationManager.setTestProviderLocation(p, loc);
            } catch (SecurityException se) {
                statusView.setText("Выбери T4 в 'Параметрах разработчика'!");
                return;
            } catch (Throwable ignored) {
                initTestProviders();
            }
        }
    }

    private void buildOverlay() {
        windowManager = (WindowManager) getSystemService(Context.WINDOW_SERVICE);
        if (windowManager == null) return;

        final WindowManager.LayoutParams params = new WindowManager.LayoutParams(
            WindowManager.LayoutParams.WRAP_CONTENT,
            WindowManager.LayoutParams.WRAP_CONTENT,
            WindowManager.LayoutParams.TYPE_APPLICATION_OVERLAY,
            WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE,
            PixelFormat.TRANSLUCENT
        );
        params.gravity = Gravity.TOP | Gravity.START;
        params.x = 40;
        params.y = 180;

        LinearLayout root = new LinearLayout(this);
        root.setOrientation(LinearLayout.VERTICAL);
        root.setPadding(24, 18, 24, 18);
        GradientDrawable bg = new GradientDrawable();
        bg.setColor(COLOR_BG);
        bg.setCornerRadius(18f);
        bg.setStroke(2, COLOR_ACCENT);
        root.setBackground(bg);

        TextView header = new TextView(this);
        header.setText("T4 // BUMP EXT (Зажми для переноса)");
        header.setTextColor(COLOR_ACCENT);
        header.setTextSize(FONT_SIZE);
        root.addView(header);

        final TextView statusText = new TextView(this);
        statusText.setTextColor(COLOR_TEXT);
        statusText.setTextSize(FONT_SIZE - 1);
        updateStatusLabel(statusText);
        root.addView(statusText);

        LinearLayout tabRow = new LinearLayout(this);
        tabRow.setOrientation(LinearLayout.HORIZONTAL);
        Button btnTabVis = makeButton("Города");
        Button btnTabProj = makeButton("Туман");
        Button btnTabCfg = makeButton("Опции");
        tabRow.addView(btnTabVis);
        tabRow.addView(btnTabProj);
        tabRow.addView(btnTabCfg);
        root.addView(tabRow);

        final LinearLayout tabVis = new LinearLayout(this);
        tabVis.setOrientation(LinearLayout.VERTICAL);

        final LinearLayout tabProj = new LinearLayout(this);
        tabProj.setOrientation(LinearLayout.VERTICAL);
        tabProj.setVisibility(View.GONE);

        final LinearLayout tabCfg = new LinearLayout(this);
        tabCfg.setOrientation(LinearLayout.VERTICAL);
        tabCfg.setVisibility(View.GONE);

        // --- TAB 1: CITIES ---
        final Button btnToggle = makeButton("Спуфинг: ВЫКЛ");
        btnToggle.setOnClickListener(v -> {
            isSpoofEnabled = !isSpoofEnabled;
            if (isSpoofEnabled) initTestProviders();
            btnToggle.setText(isSpoofEnabled ? "Спуфинг: ВКЛ" : "Спуфинг: ВЫКЛ");
            btnToggle.setTextColor(isSpoofEnabled ? COLOR_ACTIVE : COLOR_TEXT);
            updateStatusLabel(statusText);
        });
        tabVis.addView(btnToggle);

        addCity(tabVis, "Варшава", 52.2297, 21.0122, statusText);
        addCity(tabVis, "Торунь", 53.0138, 18.5984, statusText);
        addCity(tabVis, "Токио", 35.6762, 139.6503, statusText);
        addCity(tabVis, "Нью-Йорк", 40.7128, -74.0060, statusText);
        addCity(tabVis, "Париж", 48.8566, 2.3522, statusText);
        addCity(tabVis, "Лондон", 51.5074, -0.1278, statusText);

        // --- TAB 2: FOG UNLOCKER & DPAD ---
        final Button btnWalk = makeButton("Авто-открытие карты: ВЫКЛ");
        btnWalk.setOnClickListener(v -> {
            isAutoWalkEnabled = !isAutoWalkEnabled;
            btnWalk.setText(isAutoWalkEnabled ? "Авто-открытие: ВКЛ" : "Авто-открытие: ВЫКЛ");
            btnWalk.setTextColor(isAutoWalkEnabled ? COLOR_ACTIVE : COLOR_TEXT);
        });
        tabProj.addView(btnWalk);

        LinearLayout dpad = new LinearLayout(this);
        dpad.setOrientation(LinearLayout.HORIZONTAL);
        Button bN = makeButton("⬆️");
        Button bS = makeButton("⬇️");
        Button bW = makeButton("⬅️");
        Button bE = makeButton("➡️");
        bN.setOnClickListener(v -> { currentLat = clampLat(currentLat + walkStepDegrees * 3); updateStatusLabel(statusText); });
        bS.setOnClickListener(v -> { currentLat = clampLat(currentLat - walkStepDegrees * 3); updateStatusLabel(statusText); });
        bW.setOnClickListener(v -> { currentLon = clampLon(currentLon - walkStepDegrees * 3); updateStatusLabel(statusText); });
        bE.setOnClickListener(v -> { currentLon = clampLon(currentLon + walkStepDegrees * 3); updateStatusLabel(statusText); });
        dpad.addView(bN); dpad.addView(bS); dpad.addView(bW); dpad.addView(bE);
        tabProj.addView(dpad);

        // --- TAB 3: CONFIG & CLEAN EXIT ---
        Button btnSave = makeButton("Сохранить точку в JSON");
        btnSave.setOnClickListener(v -> saveConfig());
        Button btnClose = makeButton("Выгрузить и закрыть");
        btnClose.setOnClickListener(v -> cleanupAndRestore());
        tabCfg.addView(btnSave);
        tabCfg.addView(btnClose);

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
        windowManager.addView(overlayRoot, params);

        loopHandler = new Handler(Looper.getMainLooper());
        loopHandler.postDelayed(new Runnable() {
            @Override
            public void run() {
                if (overlayRoot == null) return;
                if (isSpoofEnabled) {
                    if (isAutoWalkEnabled) {
                        walkAngleRad += 0.28;
                        currentLat = clampLat(currentLat + Math.sin(walkAngleRad) * walkStepDegrees);
                        currentLon = clampLon(currentLon + Math.cos(walkAngleRad) * walkStepDegrees);
                        updateStatusLabel(statusText);
                    }
                    pushMockLocation(statusText);
                }
                loopHandler.postDelayed(this, UPDATE_INTERVAL_MS);
            }
        }, UPDATE_INTERVAL_MS);
    }

    private void addCity(LinearLayout parent, String name, final double lat, final double lon, final TextView status) {
        Button b = makeButton(name);
        b.setOnClickListener(v -> {
            currentLat = clampLat(lat);
            currentLon = clampLon(lon);
            updateStatusLabel(status);
        });
        parent.addView(b);
    }

    private Button makeButton(String text) {
        Button b = new Button(this);
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
        if (loopHandler != null) {
            loopHandler.removeCallbacksAndMessages(null);
            loopHandler = null;
        }
        String[] providers = new String[]{LocationManager.GPS_PROVIDER, LocationManager.NETWORK_PROVIDER};
        for (String p : providers) {
            try { locationManager.removeTestProvider(p); } catch (Throwable ignored) {}
        }
        if (windowManager != null && overlayRoot != null) {
            try { windowManager.removeViewImmediate(overlayRoot); } catch (Throwable ignored) {}
            overlayRoot = null;
            windowManager = null;
        }
        currentLat = 0.0;
        currentLon = 0.0;
        stopSelf();
    }

    @Override
    public void onDestroy() {
        cleanupAndRestore();
        super.onDestroy();
    }
}
"""
}

for path, content in FILES.items():
    os.makedirs(os.path.dirname(path) if os.path.dirname(path) else ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
print("T4 No-Root Project generated.")


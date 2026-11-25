import os
PK = 'android/app/src/main/java/com/teeve/teevetune/'
os.makedirs(PK, exist_ok=True)

MAIN = r'''package com.teeve.teevetune;
import android.os.Bundle;
import com.getcapacitor.BridgeActivity;
public class MainActivity extends BridgeActivity {
  @Override public void onCreate(Bundle s) {
    registerPlugin(MusicPlugin.class);
    super.onCreate(s);
    try { getBridge().getWebView().getSettings().setMediaPlaybackRequiresUserGesture(false); } catch (Exception e) {}
  }
}
'''

PLUGIN = r'''package com.teeve.teevetune;
import android.Manifest;
import android.content.Intent;
import android.database.Cursor;
import android.os.Build;
import android.provider.MediaStore;
import androidx.core.content.ContextCompat;
import com.getcapacitor.JSArray;
import com.getcapacitor.JSObject;
import com.getcapacitor.PermissionState;
import com.getcapacitor.Plugin;
import com.getcapacitor.PluginCall;
import com.getcapacitor.PluginMethod;
import com.getcapacitor.annotation.CapacitorPlugin;
import com.getcapacitor.annotation.Permission;
import com.getcapacitor.annotation.PermissionCallback;

@CapacitorPlugin(name = "Music", permissions = {
  @Permission(alias = "audio", strings = {Manifest.permission.READ_MEDIA_AUDIO}),
  @Permission(alias = "storage", strings = {Manifest.permission.READ_EXTERNAL_STORAGE}),
  @Permission(alias = "notif", strings = {Manifest.permission.POST_NOTIFICATIONS})
})
public class MusicPlugin extends Plugin {
  static MusicPlugin inst;
  @Override public void load() { inst = this; }

  static void emit(String a) {
    if (inst != null) { JSObject o = new JSObject(); o.put("a", a); inst.notifyListeners("action", o); }
  }
  private String main() { return Build.VERSION.SDK_INT >= 33 ? "audio" : "storage"; }

  @PluginMethod
  public void scan(PluginCall c) {
    if (getPermissionState(main()) != PermissionState.GRANTED) {
      String[] al = Build.VERSION.SDK_INT >= 33 ? new String[]{"audio", "notif"} : new String[]{"storage"};
      requestPermissionForAliases(al, c, "afterPerm");
    } else run(c);
  }

  @PermissionCallback
  private void afterPerm(PluginCall c) {
    if (getPermissionState(main()) == PermissionState.GRANTED) run(c); else c.reject("denied");
  }

  private void run(final PluginCall c) {
    new Thread(new Runnable() { public void run() {
      try {
        JSArray arr = new JSArray();
        String[] pr = {MediaStore.Audio.Media._ID, MediaStore.Audio.Media.TITLE, MediaStore.Audio.Media.DURATION,
          MediaStore.Audio.Media.DATE_ADDED, MediaStore.Audio.Media.DATA, MediaStore.Audio.Media.SIZE};
        Cursor q = getContext().getContentResolver().query(MediaStore.Audio.Media.EXTERNAL_CONTENT_URI, pr,
          MediaStore.Audio.Media.DURATION + ">0", null, null);
        if (q != null) {
          while (q.moveToNext()) {
            String path = q.getString(4);
            if (path == null) continue;
            String title = q.getString(1);
            if (title == null || title.length() == 0) title = path.substring(path.lastIndexOf('/') + 1);
            JSObject o = new JSObject();
            o.put("i", q.getLong(0));
            o.put("n", title);
            o.put("d", q.getLong(2) / 1000.0);
            o.put("a", q.getLong(3) * 1000L);
            o.put("p", path);
            o.put("z", q.getLong(5));
            arr.put(o);
          }
          q.close();
        }
        JSObject r = new JSObject();
        r.put("songs", arr);
        c.resolve(r);
      } catch (Exception e) { c.reject(String.valueOf(e)); }
    }}).start();
  }

  @PluginMethod
  public void now(PluginCall c) {
    Intent i = new Intent(getContext(), MusicService.class).setAction("NOW")
      .putExtra("t", c.getString("title", "")).putExtra("p", c.getBoolean("playing", false));
    try { ContextCompat.startForegroundService(getContext(), i); } catch (Exception e) {}
    c.resolve();
  }
}
'''

SERVICE = r'''package com.teeve.teevetune;
import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.app.Service;
import android.content.Intent;
import android.content.pm.ServiceInfo;
import android.graphics.drawable.Icon;
import android.media.MediaMetadata;
import android.media.session.MediaSession;
import android.media.session.PlaybackState;
import android.os.Build;
import android.os.IBinder;
import android.os.PowerManager;

public class MusicService extends Service {
  static final String CH = "music";
  MediaSession ms;
  PowerManager.WakeLock wl;

  @Override public IBinder onBind(Intent i) { return null; }

  @Override public void onCreate() {
    super.onCreate();
    if (Build.VERSION.SDK_INT >= 26) {
      ((NotificationManager) getSystemService(NOTIFICATION_SERVICE))
        .createNotificationChannel(new NotificationChannel(CH, "Reproductor", NotificationManager.IMPORTANCE_LOW));
    }
    ms = new MediaSession(this, "TeeveTune");
    ms.setCallback(new MediaSession.Callback() {
      @Override public void onPlay() { MusicPlugin.emit("play"); }
      @Override public void onPause() { MusicPlugin.emit("pause"); }
      @Override public void onSkipToNext() { MusicPlugin.emit("next"); }
      @Override public void onSkipToPrevious() { MusicPlugin.emit("prev"); }
    });
    ms.setActive(true);
    wl = ((PowerManager) getSystemService(POWER_SERVICE)).newWakeLock(PowerManager.PARTIAL_WAKE_LOCK, "tt:play");
  }

  private PendingIntent pi(String a, int code) {
    return PendingIntent.getService(this, code, new Intent(this, MusicService.class).setAction(a),
      PendingIntent.FLAG_IMMUTABLE | PendingIntent.FLAG_UPDATE_CURRENT);
  }
  private Notification.Action act(int icon, String t, String a, int code) {
    return new Notification.Action.Builder(Icon.createWithResource(this, icon), t, pi(a, code)).build();
  }

  @Override public int onStartCommand(Intent in, int flags, int id) {
    String a = in == null ? null : in.getAction();
    if ("NOW".equals(a)) {
      String t = in.getStringExtra("t");
      boolean p = in.getBooleanExtra("p", false);
      ms.setMetadata(new MediaMetadata.Builder().putString(MediaMetadata.METADATA_KEY_TITLE, t).build());
      ms.setPlaybackState(new PlaybackState.Builder()
        .setActions(PlaybackState.ACTION_PLAY | PlaybackState.ACTION_PAUSE | PlaybackState.ACTION_PLAY_PAUSE
          | PlaybackState.ACTION_SKIP_TO_NEXT | PlaybackState.ACTION_SKIP_TO_PREVIOUS)
        .setState(p ? PlaybackState.STATE_PLAYING : PlaybackState.STATE_PAUSED, 0, 1f).build());
      Notification.Builder b = Build.VERSION.SDK_INT >= 26 ? new Notification.Builder(this, CH) : new Notification.Builder(this);
      Intent li = getPackageManager().getLaunchIntentForPackage(getPackageName());
      b.setSmallIcon(android.R.drawable.ic_media_play).setContentTitle(t).setContentText("TeeveTune")
        .setOngoing(p).setShowWhen(false)
        .setContentIntent(PendingIntent.getActivity(this, 0, li, PendingIntent.FLAG_IMMUTABLE))
        .addAction(act(android.R.drawable.ic_media_previous, "Anterior", "prev", 1))
        .addAction(act(p ? android.R.drawable.ic_media_pause : android.R.drawable.ic_media_play, p ? "Pausa" : "Reproducir", "toggle", 2))
        .addAction(act(android.R.drawable.ic_media_next, "Siguiente", "next", 3))
        .setStyle(new Notification.MediaStyle().setMediaSession(ms.getSessionToken()).setShowActionsInCompactView(0, 1, 2));
      Notification n = b.build();
      if (Build.VERSION.SDK_INT >= 29) startForeground(1, n, ServiceInfo.FOREGROUND_SERVICE_TYPE_MEDIA_PLAYBACK);
      else startForeground(1, n);
      if (p) { if (!wl.isHeld()) wl.acquire(6 * 3600 * 1000L); }
      else {
        if (wl.isHeld()) wl.release();
        if (Build.VERSION.SDK_INT >= 24) stopForeground(Service.STOP_FOREGROUND_DETACH); else stopForeground(false);
      }
    } else if (a != null) {
      MusicPlugin.emit(a);
    }
    return START_NOT_STICKY;
  }

  @Override public void onDestroy() {
    if (wl != null && wl.isHeld()) wl.release();
    if (ms != null) ms.release();
    super.onDestroy();
  }
}
'''

open(PK + 'MainActivity.java', 'w').write(MAIN)
open(PK + 'MusicPlugin.java', 'w').write(PLUGIN)
open(PK + 'MusicService.java', 'w').write(SERVICE)

m = 'android/app/src/main/AndroidManifest.xml'
s = open(m).read()
perms = ''.join('    <uses-permission android:name="android.permission.%s"/>\n' % p for p in
  ['READ_MEDIA_AUDIO', 'POST_NOTIFICATIONS', 'FOREGROUND_SERVICE', 'FOREGROUND_SERVICE_MEDIA_PLAYBACK', 'WAKE_LOCK'])
perms += '    <uses-permission android:name="android.permission.READ_EXTERNAL_STORAGE" android:maxSdkVersion="32"/>\n'
if 'MusicService' not in s:
    s = s.replace('<application', perms + '    <application', 1)
    s = s.replace('</application>', '        <service android:name=".MusicService" android:exported="false" android:foregroundServiceType="mediaPlayback"/>\n    </application>', 1)
    open(m, 'w').write(s)
print('Android nativo listo')

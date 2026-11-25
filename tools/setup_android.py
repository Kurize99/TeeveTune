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
import java.util.ArrayList;
import org.json.JSONObject;

@CapacitorPlugin(name = "Music", permissions = {
  @Permission(alias = "audio", strings = {Manifest.permission.READ_MEDIA_AUDIO}),
  @Permission(alias = "storage", strings = {Manifest.permission.READ_EXTERNAL_STORAGE}),
  @Permission(alias = "notif", strings = {Manifest.permission.POST_NOTIFICATIONS})
})
public class MusicPlugin extends Plugin {
  static MusicPlugin inst;
  @Override public void load() { inst = this; }

  static void emitSt(JSObject o) {
    if (inst != null) inst.notifyListeners("st", o);
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
  public void queue(PluginCall c) {
    try {
      JSArray it = c.getArray("items");
      ArrayList<String[]> l = new ArrayList<String[]>();
      for (int k = 0; k < it.length(); k++) {
        JSONObject o = it.getJSONObject(k);
        l.add(new String[]{o.getString("i"), o.getString("p"), o.getString("n")});
      }
      MusicService.Q = l;
      MusicService.IDX = c.getInt("idx", 0);
      MusicService.SHUF = c.getBoolean("shuf", false);
      MusicService.LOOP = c.getInt("loop", 0);
      ContextCompat.startForegroundService(getContext(),
        new Intent(getContext(), MusicService.class).setAction("Q"));
      c.resolve();
    } catch (Exception e) { c.reject(String.valueOf(e)); }
  }

  @PluginMethod
  public void cmd(PluginCall c) {
    final MusicService s = MusicService.I;
    if (s != null) {
      final String k = c.getString("c", "");
      final double v = c.getDouble("v", 0.0);
      s.h.post(new Runnable() { public void run() { s.handle(k, (long) v); } });
    }
    c.resolve();
  }

  @PluginMethod
  public void mode(PluginCall c) {
    MusicService.SHUF = c.getBoolean("shuf", false);
    MusicService.LOOP = c.getInt("loop", 0);
    c.resolve();
  }

  @PluginMethod
  public void eq(PluginCall c) {
    try {
      JSArray g = c.getArray("g");
      double[] a = new double[g.length()];
      for (int k = 0; k < a.length; k++) a[k] = g.getDouble(k);
      MusicService.EQN = c.getInt("n", 5);
      MusicService.EQ = a;
      final MusicService s = MusicService.I;
      if (s != null) s.h.post(new Runnable() { public void run() { s.applyEq(); } });
    } catch (Exception e) {}
    c.resolve();
  }

  @PluginMethod
  public void state(PluginCall c) {
    MusicService s = MusicService.I;
    c.resolve(s == null ? new JSObject() : s.snap());
  }

  @PluginMethod
  public void drain(PluginCall c) {
    c.resolve(Stats.drain(getContext()));
  }
}
'''

SERVICE = r'''package com.teeve.teevetune;
import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.app.Service;
import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.content.IntentFilter;
import android.content.SharedPreferences;
import android.content.pm.ServiceInfo;
import android.graphics.drawable.Icon;
import android.media.AudioAttributes;
import android.media.AudioFocusRequest;
import android.media.AudioManager;
import android.media.MediaMetadata;
import android.media.MediaPlayer;
import android.media.audiofx.Equalizer;
import android.media.session.MediaSession;
import android.media.session.PlaybackState;
import android.os.Build;
import android.os.Handler;
import android.os.IBinder;
import android.os.Looper;
import android.os.PowerManager;
import com.getcapacitor.JSObject;
import java.util.ArrayList;
import java.util.Calendar;
import org.json.JSONArray;
import org.json.JSONObject;

public class MusicService extends Service implements AudioManager.OnAudioFocusChangeListener {
  static MusicService I;
  static volatile ArrayList<String[]> Q = new ArrayList<String[]>();
  static volatile int IDX = 0, LOOP = 0, EQN = 5;
  static volatile boolean SHUF = false;
  static volatile double[] EQ = null;
  static final int[] F5 = {60, 230, 910, 3600, 14000};
  static final int[] F10 = {31, 62, 125, 250, 500, 1000, 2000, 4000, 8000, 16000};
  static final String CH = "music";

  Handler h = new Handler(Looper.getMainLooper());
  ArrayList<String[]> q = new ArrayList<String[]>();
  MediaPlayer mp;
  Equalizer eq;
  MediaSession ms;
  AudioManager am;
  AudioFocusRequest fr;
  NotificationManager nm;
  BroadcastReceiver noisy;
  int idx, errs, ticks;
  boolean prepared, want, lostT;

  Runnable tick = new Runnable() { public void run() {
    if (isPl()) { Stats.add(MusicService.this, 1); if (++ticks % 30 == 0) Stats.save(MusicService.this); }
    send();
    h.postDelayed(this, 1000);
  }};

  @Override public IBinder onBind(Intent i) { return null; }

  @Override public void onCreate() {
    super.onCreate();
    I = this;
    nm = (NotificationManager) getSystemService(NOTIFICATION_SERVICE);
    am = (AudioManager) getSystemService(AUDIO_SERVICE);
    if (Build.VERSION.SDK_INT >= 26)
      nm.createNotificationChannel(new NotificationChannel(CH, "Reproductor", NotificationManager.IMPORTANCE_LOW));
    ms = new MediaSession(this, "TeeveTune");
    ms.setCallback(new MediaSession.Callback() {
      @Override public void onPlay() { handle("play", 0); }
      @Override public void onPause() { handle("pause", 0); }
      @Override public void onSkipToNext() { handle("next", 0); }
      @Override public void onSkipToPrevious() { handle("prev", 0); }
      @Override public void onSeekTo(long pos) { handle("seek", pos); }
    });
    ms.setActive(true);
    noisy = new BroadcastReceiver() { @Override public void onReceive(Context c, Intent i) { pause(); } };
    IntentFilter f = new IntentFilter(AudioManager.ACTION_AUDIO_BECOMING_NOISY);
    if (Build.VERSION.SDK_INT >= 33) registerReceiver(noisy, f, Context.RECEIVER_NOT_EXPORTED);
    else registerReceiver(noisy, f);
  }

  @Override public int onStartCommand(Intent in, int flags, int sid) {
    I = this;
    String a = in == null ? null : in.getAction();
    if ("Q".equals(a)) {
      q = Q; idx = IDX; want = true; lostT = false;
      fg(notif(true));
      load(idx);
    } else if (a != null) {
      handle(a, 0);
    }
    if (q.isEmpty()) stopSelf();
    return START_NOT_STICKY;
  }

  AudioAttributes attrs() {
    return new AudioAttributes.Builder().setUsage(AudioAttributes.USAGE_MEDIA)
      .setContentType(AudioAttributes.CONTENT_TYPE_MUSIC).build();
  }
  boolean isPl() { try { return mp != null && prepared && mp.isPlaying(); } catch (Exception e) { return false; } }
  boolean on() { return want && !lostT; }

  /* ---- control ---- */
  void handle(String c, long v) {
    try {
      if (c.equals("play")) { if (!on()) resume(); }
      else if (c.equals("pause")) pause();
      else if (c.equals("toggle")) { if (on()) pause(); else resume(); }
      else if (c.equals("seek")) { if (prepared) mp.seekTo((int) v); upd(); send(); }
      else if (c.equals("next")) next(false);
      else if (c.equals("prev")) prev();
    } catch (Exception e) {}
  }

  void resume() {
    want = true; lostT = false;
    if (mp == null) { if (!q.isEmpty()) load(idx); return; }
    if (prepared) start(); else upd();
  }

  boolean focus() {
    int r;
    if (Build.VERSION.SDK_INT >= 26) {
      if (fr == null) fr = new AudioFocusRequest.Builder(AudioManager.AUDIOFOCUS_GAIN)
        .setAudioAttributes(attrs()).setOnAudioFocusChangeListener(this).build();
      r = am.requestAudioFocus(fr);
    } else r = am.requestAudioFocus(this, AudioManager.STREAM_MUSIC, AudioManager.AUDIOFOCUS_GAIN);
    return r == AudioManager.AUDIOFOCUS_REQUEST_GRANTED;
  }

  void start() {
    if (mp == null || !prepared) return;
    if (!focus()) { want = false; upd(); send(); return; }
    try { mp.setVolume(1f, 1f); mp.start(); } catch (Exception e) {}
    h.removeCallbacks(tick);
    h.postDelayed(tick, 1000);
    upd(); send();
  }

  void pause() {
    want = false; lostT = false;
    try { if (prepared && mp.isPlaying()) mp.pause(); } catch (Exception e) {}
    h.removeCallbacks(tick);
    Stats.save(this);
    upd(); send();
  }

  void load(int i) {
    if (q.isEmpty()) return;
    if (i < 0 || i >= q.size()) i = 0;
    idx = i; prepared = false;
    try {
      if (mp == null) {
        mp = new MediaPlayer();
        mkEq();
        mp.setOnPreparedListener(new MediaPlayer.OnPreparedListener() { public void onPrepared(MediaPlayer m) { onPrep(); } });
        mp.setOnCompletionListener(new MediaPlayer.OnCompletionListener() { public void onCompletion(MediaPlayer m) { next(true); } });
        mp.setOnErrorListener(new MediaPlayer.OnErrorListener() { public boolean onError(MediaPlayer m, int w, int e) { errSkip(); return true; } });
      }
      mp.reset();
      mp.setWakeMode(this, PowerManager.PARTIAL_WAKE_LOCK);
      mp.setAudioAttributes(attrs());
      mp.setDataSource(q.get(idx)[1]);
      mp.prepareAsync();
    } catch (Exception e) { errSkip(); return; }
    upd(); send();
  }

  void onPrep() {
    prepared = true; errs = 0;
    Stats.log(this, q.get(idx)[0]);
    applyEq();
    if (want && !lostT) start(); else { upd(); send(); }
  }

  void errSkip() {
    prepared = false;
    if (++errs > 5 || q.size() < 2) { want = false; upd(); send(); return; }
    want = true;
    load((idx + 1) % q.size());
  }

  void next(boolean auto) {
    int n = q.size();
    if (n == 0) return;
    int j;
    if (auto && LOOP == 2) j = idx;
    else if (SHUF && n > 1) { do { j = (int) (Math.random() * n); } while (j == idx); }
    else {
      j = idx + 1;
      if (j >= n) {
        if (auto && LOOP == 0) {
          want = false; h.removeCallbacks(tick);
          try { mp.seekTo(0); } catch (Exception e) {}
          upd(); send(); return;
        }
        j = 0;
      }
    }
    want = true; lostT = false;
    load(j);
  }

  void prev() {
    try { if (prepared && mp.getCurrentPosition() > 3000) { mp.seekTo(0); upd(); send(); return; } } catch (Exception e) {}
    int n = q.size();
    if (n == 0) return;
    int j = (SHUF && n > 1) ? (int) (Math.random() * n) : (idx - 1 + n) % n;
    want = true; lostT = false;
    load(j);
  }

  @Override public void onAudioFocusChange(int c) {
    try {
      if (c == AudioManager.AUDIOFOCUS_LOSS) pause();
      else if (c == AudioManager.AUDIOFOCUS_LOSS_TRANSIENT) {
        if (isPl()) { lostT = true; mp.pause(); upd(); send(); }
      } else if (c == AudioManager.AUDIOFOCUS_LOSS_TRANSIENT_CAN_DUCK) {
        if (mp != null) mp.setVolume(0.25f, 0.25f);
      } else if (c == AudioManager.AUDIOFOCUS_GAIN) {
        if (mp != null) mp.setVolume(1f, 1f);
        if (lostT) { lostT = false; if (want && prepared) { mp.start(); upd(); send(); } }
      }
    } catch (Exception e) {}
  }

  /* ---- ecualizador (Equalizer del sistema; las bandas de la interfaz se interpolan) ---- */
  void mkEq() {
    try { eq = new Equalizer(0, mp.getAudioSessionId()); eq.setEnabled(true); applyEq(); }
    catch (Throwable t) { eq = null; }
  }

  static double interp(double f, int[] fr, double[] g) {
    if (g == null || g.length != fr.length) return 0;
    if (f <= fr[0]) return g[0];
    for (int i = 1; i < fr.length; i++) {
      if (f <= fr[i]) {
        double a = Math.log(fr[i - 1]), b = Math.log(fr[i]);
        double t = (Math.log(f) - a) / (b - a);
        return g[i - 1] + (g[i] - g[i - 1]) * t;
      }
    }
    return g[g.length - 1];
  }

  void applyEq() {
    if (eq == null || EQ == null) return;
    try {
      short nb = eq.getNumberOfBands();
      short[] r = eq.getBandLevelRange();
      int[] fr = EQN == 10 ? F10 : F5;
      for (short b = 0; b < nb; b++) {
        double cf = eq.getCenterFreq(b) / 1000.0;
        int mb = (int) Math.round(interp(cf, fr, EQ) * 100);
        mb = Math.max(r[0], Math.min(r[1], mb));
        eq.setBandLevel(b, (short) mb);
      }
    } catch (Throwable t) {}
  }

  /* ---- estado, sesion y notificacion ---- */
  JSObject snap() {
    JSObject o = new JSObject();
    try {
      if (!q.isEmpty() && idx < q.size()) o.put("id", q.get(idx)[0]);
      o.put("p", on());
      o.put("t", prepared ? mp.getCurrentPosition() : 0);
      o.put("d", prepared ? mp.getDuration() : 0);
      o.put("sh", SHUF);
      o.put("lp", LOOP);
    } catch (Exception e) {}
    return o;
  }

  void send() { MusicPlugin.emitSt(snap()); }

  PendingIntent pi(String a, int code) {
    return PendingIntent.getService(this, code, new Intent(this, MusicService.class).setAction(a),
      PendingIntent.FLAG_IMMUTABLE | PendingIntent.FLAG_UPDATE_CURRENT);
  }
  Notification.Action act(int icon, String t, String a, int code) {
    return new Notification.Action.Builder(Icon.createWithResource(this, icon), t, pi(a, code)).build();
  }

  Notification notif(boolean p) {
    String t = q.isEmpty() || idx >= q.size() ? "TeeveTune" : q.get(idx)[2];
    Notification.Builder b = Build.VERSION.SDK_INT >= 26 ? new Notification.Builder(this, CH) : new Notification.Builder(this);
    Intent li = getPackageManager().getLaunchIntentForPackage(getPackageName());
    b.setSmallIcon(android.R.drawable.ic_media_play).setContentTitle(t).setContentText("TeeveTune")
      .setOngoing(p).setShowWhen(false).setOnlyAlertOnce(true)
      .addAction(act(android.R.drawable.ic_media_previous, "Anterior", "prev", 1))
      .addAction(act(p ? android.R.drawable.ic_media_pause : android.R.drawable.ic_media_play, p ? "Pausa" : "Reproducir", "toggle", 2))
      .addAction(act(android.R.drawable.ic_media_next, "Siguiente", "next", 3))
      .setStyle(new Notification.MediaStyle().setMediaSession(ms.getSessionToken()).setShowActionsInCompactView(0, 1, 2));
    if (li != null) b.setContentIntent(PendingIntent.getActivity(this, 0, li, PendingIntent.FLAG_IMMUTABLE));
    return b.build();
  }

  void fg(Notification n) {
    if (Build.VERSION.SDK_INT >= 29) startForeground(1, n, ServiceInfo.FOREGROUND_SERVICE_TYPE_MEDIA_PLAYBACK);
    else startForeground(1, n);
  }

  void upd() {
    if (q.isEmpty() || idx >= q.size()) return;
    long pos = 0, dur = 0;
    try { if (prepared) { pos = mp.getCurrentPosition(); dur = mp.getDuration(); } } catch (Exception e) {}
    boolean p = on();
    ms.setMetadata(new MediaMetadata.Builder().putString(MediaMetadata.METADATA_KEY_TITLE, q.get(idx)[2])
      .putLong(MediaMetadata.METADATA_KEY_DURATION, dur).build());
    ms.setPlaybackState(new PlaybackState.Builder()
      .setActions(PlaybackState.ACTION_PLAY | PlaybackState.ACTION_PAUSE | PlaybackState.ACTION_PLAY_PAUSE
        | PlaybackState.ACTION_SKIP_TO_NEXT | PlaybackState.ACTION_SKIP_TO_PREVIOUS | PlaybackState.ACTION_SEEK_TO)
      .setState(p ? PlaybackState.STATE_PLAYING : PlaybackState.STATE_PAUSED, pos, p ? 1f : 0f).build());
    Notification n = notif(p);
    if (want) fg(n);
    else {
      if (Build.VERSION.SDK_INT >= 24) stopForeground(Service.STOP_FOREGROUND_DETACH); else stopForeground(false);
      nm.notify(1, n);
    }
  }

  @Override public void onDestroy() {
    h.removeCallbacksAndMessages(null);
    Stats.save(this);
    try { unregisterReceiver(noisy); } catch (Exception e) {}
    try { if (mp != null) mp.release(); } catch (Exception e) {}
    try { if (eq != null) eq.release(); } catch (Exception e) {}
    try { ms.release(); } catch (Exception e) {}
    I = null;
    super.onDestroy();
  }
}

/* Historial y tiempo escuchado se guardan aqui aunque la pantalla este apagada; la app los recoge despues. */
class Stats {
  static final Object L = new Object();
  static JSONArray h = new JSONArray();
  static JSONObject d = new JSONObject();
  static boolean loaded;

  static void load(Context c) {
    if (loaded) return;
    loaded = true;
    try {
      SharedPreferences p = c.getSharedPreferences("tt", 0);
      h = new JSONArray(p.getString("h", "[]"));
      d = new JSONObject(p.getString("d", "{}"));
    } catch (Exception e) {}
  }
  static void save(Context c) {
    synchronized (L) {
      load(c);
      c.getSharedPreferences("tt", 0).edit().putString("h", h.toString()).putString("d", d.toString()).apply();
    }
  }
  static String key() {
    Calendar c = Calendar.getInstance();
    return c.get(Calendar.YEAR) + "-" + (c.get(Calendar.MONTH) + 1) + "-" + c.get(Calendar.DAY_OF_MONTH);
  }
  static void log(Context c, String id) {
    synchronized (L) {
      load(c);
      try { JSONObject o = new JSONObject(); o.put("id", id); o.put("t", System.currentTimeMillis()); h.put(o); } catch (Exception e) {}
    }
    save(c);
  }
  static void add(Context c, double s) {
    synchronized (L) {
      load(c);
      try { String k = key(); d.put(k, d.optDouble(k, 0) + s); } catch (Exception e) {}
    }
  }
  static JSObject drain(Context c) {
    synchronized (L) {
      load(c);
      JSObject r = new JSObject();
      try { r.put("h", h); r.put("d", d); } catch (Exception e) {}
      h = new JSONArray();
      d = new JSONObject();
      c.getSharedPreferences("tt", 0).edit().putString("h", "[]").putString("d", "{}").apply();
      return r;
    }
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

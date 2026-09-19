package app.dze.downloader;

import android.app.Activity;
import android.content.ClipboardManager;
import android.content.Intent;
import android.net.Uri;
import android.os.Bundle;
import android.webkit.JavascriptInterface;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;

public class MainActivity extends Activity {
    private static final int REQ_DIR = 41;
    private DownloadEngine engine;
    private WebView web;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        engine = new DownloadEngine(this);
        web = new WebView(this);
        WebSettings s = web.getSettings();
        s.setJavaScriptEnabled(true);
        s.setDomStorageEnabled(true);
        web.setWebViewClient(new WebViewClient());
        web.addJavascriptInterface(new Bridge(), "DZE");
        web.loadUrl("file:///android_asset/index.html");
        setContentView(web);
    }

    @Override
    protected void onActivityResult(int requestCode, int resultCode, Intent data) {
        super.onActivityResult(requestCode, resultCode, data);
        if (requestCode == REQ_DIR && resultCode == RESULT_OK
                && data != null && data.getData() != null) {
            Uri uri = data.getData();
            final int take = Intent.FLAG_GRANT_READ_URI_PERMISSION
                    | Intent.FLAG_GRANT_WRITE_URI_PERMISSION;
            try {
                getContentResolver().takePersistableUriPermission(uri, take);
            } catch (Exception ignored) {
            }
            getSharedPreferences("dze", MODE_PRIVATE)
                    .edit().putString("save_tree", uri.toString()).apply();
            engine.reloadSaveDir();
        }
    }

    @Override
    protected void onDestroy() {
        if (isFinishing() && engine != null) engine.shutdown();
        super.onDestroy();
    }

    class Bridge {
        @JavascriptInterface
        public String start(String url) {
            return engine.addTask(url);
        }

        @JavascriptInterface
        public void stop() {
            engine.stopAll();
        }

        @JavascriptInterface
        public String status() {
            return engine.statusJson();
        }

        @JavascriptInterface
        public String paste() {
            ClipboardManager cm = (ClipboardManager) getSystemService(CLIPBOARD_SERVICE);
            if (cm != null && cm.hasPrimaryClip() && cm.getPrimaryClip().getItemCount() > 0) {
                CharSequence text = cm.getPrimaryClip().getItemAt(0).coerceToText(getApplicationContext());
                return text == null ? "" : text.toString();
            }
            return "";
        }

        @JavascriptInterface
        public void pickDir() {
            runOnUiThread(new Runnable() {
                @Override
                public void run() {
                    startActivityForResult(
                            new Intent(Intent.ACTION_OPEN_DOCUMENT_TREE), REQ_DIR);
                }
            });
        }

        @JavascriptInterface
        public void resetDir() {
            getSharedPreferences("dze", MODE_PRIVATE)
                    .edit().remove("save_tree").apply();
            engine.reloadSaveDir();
        }
    }
}

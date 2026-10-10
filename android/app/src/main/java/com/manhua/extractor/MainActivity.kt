package com.manhua.extractor

import android.Manifest
import android.annotation.SuppressLint
import android.content.pm.PackageManager
import android.os.Build
import android.os.Bundle
import android.os.Environment
import android.view.View
import android.view.ViewGroup
import android.webkit.WebChromeClient
import android.webkit.WebResourceRequest
import android.webkit.WebSettings
import android.webkit.WebView
import android.webkit.WebViewClient
import android.widget.LinearLayout
import android.widget.TextView
import androidx.activity.OnBackPressedCallback
import androidx.appcompat.app.AppCompatActivity
import androidx.core.app.ActivityCompat
import androidx.core.content.ContextCompat
import androidx.lifecycle.lifecycleScope
import com.chaquo.python.Python
import com.chaquo.python.android.AndroidPlatform
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import java.net.HttpURLConnection
import java.net.URL

class MainActivity : AppCompatActivity() {

    private lateinit var webView: WebView
    private lateinit var splashContainer: LinearLayout
    private lateinit var fullscreenContainer: ViewGroup
    private lateinit var splashStatusText: TextView

    private var customView: View? = null
    private var customViewCallback: WebChromeClient.CustomViewCallback? = null

    private val localServerPort = 8000
    private val localServerUrl = "http://127.0.0.1:$localServerPort/"

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_main)

        webView = findViewById(R.id.webView)
        splashContainer = findViewById(R.id.splashContainer)
        fullscreenContainer = findViewById(R.id.fullscreenContainer)
        splashStatusText = findViewById(R.id.splashStatusText)

        setupBackNavigation()
        requestNotificationPermission()
        setupWebView()

        startPythonBackend()
        pollServerAndLoadUi()
    }

    private fun requestNotificationPermission() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            if (ContextCompat.checkSelfPermission(this, Manifest.permission.POST_NOTIFICATIONS)
                != PackageManager.PERMISSION_GRANTED
            ) {
                ActivityCompat.requestPermissions(
                    this,
                    arrayOf(Manifest.permission.POST_NOTIFICATIONS),
                    101
                )
            }
        }
    }

    private fun startPythonBackend() {
        try {
            if (!Python.isStarted()) {
                Python.start(AndroidPlatform(this))
            }
            val py = Python.getInstance()
            val internalDir = filesDir.absolutePath
            val externalDownloadDir = getExternalFilesDir(Environment.DIRECTORY_DOWNLOADS)?.absolutePath
                ?: (Environment.getExternalStoragePublicDirectory(Environment.DIRECTORY_DOWNLOADS).absolutePath + "/Manhua")

            val entryModule = py.getModule("android_entry")
            entryModule.callAttr("start_server_thread", internalDir, externalDownloadDir, localServerPort)
        } catch (e: Exception) {
            splashStatusText.text = "Error starting Python: ${e.message}"
        }
    }

    @SuppressLint("SetJavaScriptEnabled")
    private fun setupWebView() {
        webView.apply {
            setLayerType(View.LAYER_TYPE_HARDWARE, null)
            settings.apply {
                javaScriptEnabled = true
                domStorageEnabled = true
                databaseEnabled = true
                allowFileAccess = true
                allowContentAccess = true
                cacheMode = WebSettings.LOAD_DEFAULT
                useWideViewPort = true
                loadWithOverviewMode = true
                builtInZoomControls = false
                displayZoomControls = false
                mediaPlaybackRequiresUserGesture = false
            }

            webViewClient = object : WebViewClient() {
                override fun shouldOverrideUrlLoading(view: WebView?, request: WebResourceRequest?): Boolean {
                    return false
                }
            }

            webChromeClient = object : WebChromeClient() {
                override fun onShowCustomView(view: View?, callback: CustomViewCallback?) {
                    if (customView != null) {
                        callback?.onCustomViewHidden()
                        return
                    }
                    customView = view
                    customViewCallback = callback
                    fullscreenContainer.addView(view)
                    fullscreenContainer.visibility = View.VISIBLE
                    webView.visibility = View.GONE
                }

                override fun onHideCustomView() {
                    fullscreenContainer.removeView(customView)
                    fullscreenContainer.visibility = View.GONE
                    webView.visibility = View.VISIBLE
                    customView = null
                    customViewCallback?.onCustomViewHidden()
                }
            }
        }
    }

    private fun pollServerAndLoadUi() {
        lifecycleScope.launch(Dispatchers.IO) {
            var isReady = false
            var attempts = 0
            val maxAttempts = 60

            while (!isReady && attempts < maxAttempts) {
                attempts++
                try {
                    val url = URL("http://127.0.0.1:$localServerPort/api/health")
                    val conn = url.openConnection() as HttpURLConnection
                    conn.connectTimeout = 1000
                    conn.readTimeout = 1000
                    conn.requestMethod = "GET"
                    val code = conn.responseCode
                    conn.disconnect()
                    if (code == 200) {
                        isReady = true
                    }
                } catch (_: Exception) {
                    delay(300)
                }
            }

            withContext(Dispatchers.Main) {
                if (isReady) {
                    splashContainer.visibility = View.GONE
                    webView.visibility = View.VISIBLE
                    webView.loadUrl(localServerUrl)
                } else {
                    splashStatusText.text = "Server boot timeout. Please restart the app."
                }
            }
        }
    }

    private fun setupBackNavigation() {
        onBackPressedDispatcher.addCallback(this, object : OnBackPressedCallback(true) {
            override fun handleOnBackPressed() {
                if (customView != null) {
                    webView.webChromeClient?.onHideCustomView()
                } else {
                    // Check if reader view or modal is open in WebView
                    webView.evaluateJavascript(
                        "(function() { " +
                        "  var rv = document.getElementById('reader-view'); " +
                        "  if (rv && !rv.classList.contains('hidden')) { " +
                        "    var rc = document.getElementById('reader-close'); " +
                        "    if (rc) { rc.click(); return true; } " +
                        "  } " +
                        "  var sm = document.getElementById('series-modal'); " +
                        "  if (sm && !sm.classList.contains('hidden')) { " +
                        "    var sc = document.getElementById('modal-close'); " +
                        "    if (sc) { sc.click(); return true; } " +
                        "  } " +
                        "  var pm = document.getElementById('phone-modal'); " +
                        "  if (pm && !pm.classList.contains('hidden')) { " +
                        "    var pc = document.getElementById('phone-modal-close'); " +
                        "    if (pc) { pc.click(); return true; } " +
                        "  } " +
                        "  return false; " +
                        "})()"
                    ) { result ->
                        if (result != "true") {
                            if (webView.canGoBack()) {
                                webView.goBack()
                            } else {
                                isEnabled = false
                                onBackPressedDispatcher.onBackPressed()
                            }
                        }
                    }
                }
            }
        })
    }

    override fun onDestroy() {
        super.onDestroy()
        webView.destroy()
    }
}

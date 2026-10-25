package com.manhua.extractor

import android.Manifest
import android.annotation.SuppressLint
import android.app.Activity
import android.app.AlertDialog
import android.app.DownloadManager
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.os.Environment
import android.util.Log
import android.view.View
import android.view.ViewGroup
import android.webkit.ConsoleMessage
import android.webkit.JsResult
import android.webkit.URLUtil
import android.webkit.ValueCallback
import android.webkit.WebChromeClient
import android.webkit.WebResourceRequest
import android.webkit.WebSettings
import android.webkit.WebView
import android.webkit.WebViewClient
import android.widget.LinearLayout
import android.widget.TextView
import android.widget.Toast
import androidx.activity.OnBackPressedCallback
import androidx.activity.result.contract.ActivityResultContracts
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

    private var fileChooserCallback: ValueCallback<Array<Uri>>? = null

    private val filePickerLauncher = registerForActivityResult(
        ActivityResultContracts.StartActivityForResult()
    ) { result ->
        if (result.resultCode == Activity.RESULT_OK) {
            val data = result.data
            val uris: Array<Uri>? = when {
                data?.clipData != null -> {
                    val count = data.clipData!!.itemCount
                    Array(count) { i -> data.clipData!!.getItemAt(i).uri }
                }
                data?.data != null -> arrayOf(data.data!!)
                else -> null
            }
            fileChooserCallback?.onReceiveValue(uris)
        } else {
            fileChooserCallback?.onReceiveValue(null)
        }
        fileChooserCallback = null
    }

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
        CloudflareResolver.init(this)

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
                cacheMode = WebSettings.LOAD_NO_CACHE
                useWideViewPort = false
                loadWithOverviewMode = false
                textZoom = 100
                builtInZoomControls = false
                displayZoomControls = false
                mediaPlaybackRequiresUserGesture = false
            }
            clearCache(true)

            addJavascriptInterface(AndroidWebAppInterface(this@MainActivity), "AndroidApp")

            webViewClient = object : WebViewClient() {
                override fun shouldOverrideUrlLoading(view: WebView?, request: WebResourceRequest?): Boolean {
                    return false
                }
            }

            webChromeClient = object : WebChromeClient() {
                override fun onConsoleMessage(consoleMessage: ConsoleMessage?): Boolean {
                    Log.d("WebConsole", "[${consoleMessage?.messageLevel()}] ${consoleMessage?.message()} -- line ${consoleMessage?.lineNumber()}")
                    return true
                }

                override fun onJsAlert(view: WebView?, url: String?, message: String?, result: JsResult?): Boolean {
                    AlertDialog.Builder(this@MainActivity)
                        .setTitle("Manhua Extractor")
                        .setMessage(message ?: "")
                        .setPositiveButton(android.R.string.ok) { _, _ -> result?.confirm() }
                        .setOnCancelListener { result?.cancel() }
                        .show()
                    return true
                }

                override fun onShowFileChooser(
                    webView: WebView?,
                    filePathCallback: ValueCallback<Array<Uri>>?,
                    fileChooserParams: FileChooserParams?
                ): Boolean {
                    fileChooserCallback?.onReceiveValue(null)
                    fileChooserCallback = filePathCallback

                    val intent = Intent(Intent.ACTION_GET_CONTENT).apply {
                        type = "*/*"
                        addCategory(Intent.CATEGORY_OPENABLE)
                        putExtra(Intent.EXTRA_ALLOW_MULTIPLE, true)
                        putExtra(Intent.EXTRA_MIME_TYPES, arrayOf(
                            "application/zip",
                            "application/x-zip-compressed",
                            "application/x-zip",
                            "application/octet-stream",
                            "*/*"
                        ))
                    }

                    return try {
                        filePickerLauncher.launch(Intent.createChooser(intent, "Select Backup Archive (.zip)"))
                        true
                    } catch (e: Exception) {
                        Log.e("MainActivity", "Failed to launch file picker: ${e.message}", e)
                        fileChooserCallback?.onReceiveValue(null)
                        fileChooserCallback = null
                        false
                    }
                }

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

            setDownloadListener { url, userAgent, contentDisposition, mimetype, contentLength ->
                try {
                    val fileName = URLUtil.guessFileName(url, contentDisposition, mimetype ?: "application/zip")
                    val request = DownloadManager.Request(Uri.parse(url)).apply {
                        setMimeType(mimetype ?: "application/zip")
                        setDescription("Saving Manhua Backup Archive...")
                        setTitle(fileName)
                        setNotificationVisibility(DownloadManager.Request.VISIBILITY_VISIBLE_NOTIFY_COMPLETED)
                        setDestinationInExternalPublicDir(
                            Environment.DIRECTORY_DOWNLOADS,
                            "Manhua/Backups/$fileName"
                        )
                    }
                    val dm = getSystemService(Context.DOWNLOAD_SERVICE) as DownloadManager
                    dm.enqueue(request)
                    Toast.makeText(this@MainActivity, "Saving $fileName to Downloads/Manhua/Backups", Toast.LENGTH_SHORT).show()
                } catch (e: Exception) {
                    Log.e("WebView", "Download error: ${e.message}", e)
                    Toast.makeText(this@MainActivity, "Download failed: ${e.message}", Toast.LENGTH_SHORT).show()
                }
            }
        }
    }

    private fun pollServerAndLoadUi() {
        lifecycleScope.launch(Dispatchers.IO) {
            var isReady = false
            var attempts = 0
            val maxAttempts = 150
            var pyError: String? = null

            while (!isReady && attempts < maxAttempts) {
                attempts++
                try {
                    val url = URL("http://127.0.0.1:$localServerPort/api/health")
                    val conn = url.openConnection() as HttpURLConnection
                    conn.connectTimeout = 800
                    conn.readTimeout = 800
                    conn.requestMethod = "GET"
                    val code = conn.responseCode
                    conn.disconnect()
                    if (code == 200) {
                        isReady = true
                    }
                } catch (_: Exception) {
                    // Check if Python reported a fatal error
                    try {
                        if (Python.isStarted()) {
                            val py = Python.getInstance()
                            val entryModule = py.getModule("android_entry")
                            val lastErr = entryModule.callAttr("get_last_error")?.toString()
                            if (!lastErr.isNullOrBlank() && lastErr != "None") {
                                pyError = lastErr
                                break
                            }
                        }
                    } catch (_: Exception) {
                    }
                    delay(300)
                }
            }

            withContext(Dispatchers.Main) {
                if (isReady) {
                    splashContainer.visibility = View.GONE
                    webView.visibility = View.VISIBLE
                    webView.loadUrl(localServerUrl)
                } else if (!pyError.isNullOrBlank()) {
                    splashStatusText.text = "Python Startup Error:\n$pyError"
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
                    // Check if reader view, drawer, or modal is open in WebView
                    webView.evaluateJavascript(
                        "(function() { " +
                        "  var dr = document.getElementById('sidebar-drawer'); " +
                        "  if (dr && dr.classList.contains('open')) { " +
                        "    var dc = document.getElementById('drawer-close'); " +
                        "    if (dc) { dc.click(); return true; } " +
                        "  } " +
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

    fun notifyUpdateProgress(percent: Int) {
        webView.evaluateJavascript("if (window.onUpdateDownloadProgress) { window.onUpdateDownloadProgress($percent); }", null)
    }

    fun notifyUpdateError(error: String) {
        val safeErr = org.json.JSONObject.quote(error)
        webView.evaluateJavascript("if (window.onUpdateDownloadError) { window.onUpdateDownloadError($safeErr); }", null)
    }

    override fun onResume() {
        super.onResume()
        try {
            if (FileUtils.isWaitingForUnknownAppPermission) {
                FileUtils.isWaitingForUnknownAppPermission = false
                if (Build.VERSION.SDK_INT < Build.VERSION_CODES.O || packageManager.canRequestPackageInstalls()) {
                    val updateFile = java.io.File(cacheDir, "updates/update.apk")
                    if (updateFile.exists() && updateFile.length() > 0L) {
                        webView.evaluateJavascript("if (window.onUpdateReadyToInstall) { window.onUpdateReadyToInstall(); }", null)
                    }
                }
            }
        } catch (_: Exception) {
        }
    }

    override fun onDestroy() {
        super.onDestroy()
        webView.destroy()
    }
}

package com.manhua.extractor

import android.annotation.SuppressLint
import android.content.Context
import android.os.Handler
import android.os.Looper
import android.util.Log
import android.webkit.CookieManager
import android.webkit.WebSettings
import android.webkit.WebView
import android.webkit.WebViewClient
import org.json.JSONObject
import java.net.URI
import java.util.concurrent.CountDownLatch
import java.util.concurrent.TimeUnit
import java.util.concurrent.atomic.AtomicBoolean
import java.util.concurrent.atomic.AtomicReference

/**
 * Thread-safe Native Android Cloudflare & Turnstile Resolver.
 * Uses an authentic Android Chromium WebView on the main looper to clear Cloudflare challenges
 * and returns cookies, User-Agent, and page HTML across Chaquopy without freezing the UI.
 */
object CloudflareResolver {
    private const val TAG = "CloudflareResolver"
    private var appContext: Context? = null
    private val mainHandler = Handler(Looper.getMainLooper())

    fun init(context: Context) {
        this.appContext = context.applicationContext
    }

    /**
     * Synchronous blocking resolution called from background worker threads (e.g. Python FastAPI).
     * Returns a JSON string with:
     * { "success": true/false, "status": 200, "cookies": "...", "user_agent": "...", "html": "..." }
     */
    @JvmStatic
    @JvmOverloads
    fun resolveUrl(targetUrl: String, timeoutSeconds: Long = 18): String {
        val context = appContext ?: run {
            Log.e(TAG, "CloudflareResolver appContext is null, cannot instantiate WebView")
            val err = JSONObject()
            err.put("success", false)
            err.put("error", "Context not initialized")
            return err.toString()
        }

        val latch = CountDownLatch(1)
        val resultRef = AtomicReference<String?>(null)
        val isResolved = AtomicBoolean(false)
        var backgroundWebView: WebView? = null

        mainHandler.post {
            try {
                val wv = WebView(context)
                backgroundWebView = wv
                val cookieManager = CookieManager.getInstance()
                cookieManager.setAcceptCookie(true)
                cookieManager.setAcceptThirdPartyCookies(wv, true)

                val settings = wv.settings
                settings.javaScriptEnabled = true
                settings.domStorageEnabled = true
                settings.databaseEnabled = true
                settings.cacheMode = WebSettings.LOAD_DEFAULT
                settings.userAgentString = WebSettings.getDefaultUserAgent(context)
                val ua = settings.userAgentString

                // Periodic cookie poller in case Turnstile solves via background script
                val pollRunnable = object : Runnable {
                    override fun run() {
                        if (isResolved.get()) return
                        val currentCookies = cookieManager.getCookie(targetUrl) ?: ""
                        if (currentCookies.contains("cf_clearance")) {
                            if (isResolved.compareAndSet(false, true)) {
                                wv.evaluateJavascript("(function(){return document.documentElement.outerHTML;})();") { htmlJson ->
                                    val unquotedHtml = cleanJsString(htmlJson)
                                    val res = JSONObject()
                                    res.put("success", true)
                                    res.put("status", 200)
                                    res.put("cookies", currentCookies)
                                    res.put("user_agent", ua)
                                    res.put("html", unquotedHtml)
                                    resultRef.set(res.toString())
                                    latch.countDown()
                                }
                            }
                            return
                        }
                        mainHandler.postDelayed(this, 500)
                    }
                }
                mainHandler.postDelayed(pollRunnable, 500)

                wv.webViewClient = object : WebViewClient() {
                    override fun onPageFinished(view: WebView?, url: String?) {
                        super.onPageFinished(view, url)
                        val cookies = cookieManager.getCookie(url ?: targetUrl) ?: ""
                        val hasClearance = cookies.contains("cf_clearance")

                        // Evaluate title/content to check if challenge cleared
                        view?.evaluateJavascript("(function(){return JSON.stringify({title: document.title, html: document.documentElement.outerHTML});})();") { evalRes ->
                            if (isResolved.get()) return@evaluateJavascript
                            try {
                                val obj = if (!evalRes.isNullOrBlank() && evalRes != "null") JSONObject(evalRes) else null
                                val title = obj?.optString("title", "") ?: ""
                                val html = obj?.optString("html", "") ?: ""

                                val isStillChallenge = title.contains("Just a moment", ignoreCase = true) ||
                                        html.contains("challenges.cloudflare.com") ||
                                        html.contains("cf-turnstile")

                                if (hasClearance || (!isStillChallenge && html.length > 500)) {
                                    if (isResolved.compareAndSet(false, true)) {
                                        mainHandler.removeCallbacks(pollRunnable)
                                        val res = JSONObject()
                                        res.put("success", true)
                                        res.put("status", 200)
                                        res.put("cookies", cookies)
                                        res.put("user_agent", ua)
                                        res.put("html", html)
                                        resultRef.set(res.toString())
                                        latch.countDown()
                                    }
                                }
                            } catch (e: Exception) {
                                Log.w(TAG, "Error in evaluateJavascript callback: ${e.message}")
                            }
                        }
                    }
                }

                wv.loadUrl(targetUrl)
            } catch (e: Exception) {
                Log.e(TAG, "Error initializing background WebView: ${e.message}", e)
                val res = JSONObject()
                res.put("success", false)
                res.put("error", e.message ?: "WebView initialization error")
                resultRef.set(res.toString())
                latch.countDown()
            }
        }

        // Wait with timeout
        val completed = latch.await(timeoutSeconds, TimeUnit.SECONDS)

        // Clean up WebView on Main thread
        mainHandler.post {
            try {
                backgroundWebView?.stopLoading()
                backgroundWebView?.loadUrl("about:blank")
                backgroundWebView?.destroy()
            } catch (_: Exception) {
            }
        }

        if (!completed && resultRef.get() == null) {
            val res = JSONObject()
            res.put("success", false)
            res.put("error", "Timeout waiting for Cloudflare resolution after $timeoutSeconds seconds")
            return res.toString()
        }

        return resultRef.get() ?: JSONObject().apply {
            put("success", false)
            put("error", "Unknown resolution failure")
        }.toString()
    }

    /**
     * Fast non-blocking check for existing cached cookies for domain.
     */
    @JvmStatic
    fun getCachedCookies(domainUrl: String): String? {
        return CookieManager.getInstance().getCookie(domainUrl)
    }

    private fun cleanJsString(raw: String?): String {
        if (raw.isNullOrBlank() || raw == "null") return ""
        if (raw.startsWith("\"") && raw.endsWith("\"") && raw.length >= 2) {
            return try {
                JSONObject("{\"v\":$raw}").getString("v")
            } catch (_: Exception) {
                raw.substring(1, raw.length - 1)
            }
        }
        return raw
    }
}


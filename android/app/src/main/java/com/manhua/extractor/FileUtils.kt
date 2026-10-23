package com.manhua.extractor

import android.app.DownloadManager
import android.content.ContentValues
import android.content.Context
import android.content.Intent
import android.media.MediaScannerConnection
import android.net.Uri
import android.os.Build
import android.os.Environment
import android.os.Handler
import android.os.Looper
import android.provider.MediaStore
import android.provider.Settings
import android.util.Log
import android.webkit.JavascriptInterface
import android.widget.Toast
import androidx.core.content.FileProvider
import java.io.File
import java.net.HttpURLConnection
import java.net.URL
import java.util.concurrent.Executors

object FileUtils {

    private const val TAG = "FileUtils"

    fun getBackupDirectory(context: Context): File {
        val downloadDir = context.getExternalFilesDir(Environment.DIRECTORY_DOWNLOADS)
            ?: File(context.filesDir, "downloads")
        val backupDir = File(downloadDir, "Backups")
        if (!backupDir.exists()) {
            backupDir.mkdirs()
        }
        return backupDir
    }

    fun scanMediaFile(context: Context, file: File) {
        if (!file.exists()) return
        val mimeType = when {
            file.name.endsWith(".cbz", true) -> "application/x-cbz"
            file.name.endsWith(".zip", true) -> "application/zip"
            else -> "application/pdf"
        }
        MediaScannerConnection.scanFile(
            context,
            arrayOf(file.absolutePath),
            arrayOf(mimeType)
        ) { _, _ -> }
    }

    @JvmStatic
    fun saveZipToPublicDownloads(context: Context, sourceFile: File): Uri? {
        if (!sourceFile.exists()) return null

        try {
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
                val contentValues = ContentValues().apply {
                    put(MediaStore.MediaColumns.DISPLAY_NAME, sourceFile.name)
                    put(MediaStore.MediaColumns.MIME_TYPE, "application/zip")
                    put(MediaStore.MediaColumns.RELATIVE_PATH, "${Environment.DIRECTORY_DOWNLOADS}/Manhua/Backups")
                    put(MediaStore.MediaColumns.IS_PENDING, 1)
                }

                val resolver = context.contentResolver
                val uri = resolver.insert(MediaStore.Downloads.EXTERNAL_CONTENT_URI, contentValues)
                if (uri != null) {
                    resolver.openOutputStream(uri)?.use { out ->
                        sourceFile.inputStream().use { input ->
                            input.copyTo(out)
                        }
                    }
                    contentValues.clear()
                    contentValues.put(MediaStore.MediaColumns.IS_PENDING, 0)
                    resolver.update(uri, contentValues, null, null)
                    scanMediaFile(context, sourceFile)
                    Log.d(TAG, "Copied backup to MediaStore public downloads: ${sourceFile.name}")
                    return uri
                }
            } else {
                val publicBackups = File(
                    Environment.getExternalStoragePublicDirectory(Environment.DIRECTORY_DOWNLOADS),
                    "Manhua/Backups"
                )
                if (!publicBackups.exists()) {
                    publicBackups.mkdirs()
                }
                val dest = File(publicBackups, sourceFile.name)
                sourceFile.copyTo(dest, overwrite = true)
                scanMediaFile(context, dest)
                Log.d(TAG, "Copied backup to public directory: ${dest.absolutePath}")
                return Uri.fromFile(dest)
            }
        } catch (e: Exception) {
            Log.e(TAG, "Failed to copy backup to public storage: ${e.message}", e)
        }

        scanMediaFile(context, sourceFile)
        return Uri.fromFile(sourceFile)
    }

    @JvmStatic
    fun openBackupFolder(context: Context) {
        val backupDir = getBackupDirectory(context)
        val publicDir = File(
            Environment.getExternalStoragePublicDirectory(Environment.DIRECTORY_DOWNLOADS),
            "Manhua/Backups"
        )
        val targetDir = if (publicDir.exists() && (publicDir.listFiles()?.isNotEmpty() == true)) {
            publicDir
        } else {
            backupDir
        }

        // 1. Try launching Downloads view
        try {
            val intent = Intent(DownloadManager.ACTION_VIEW_DOWNLOADS).apply {
                addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
            }
            context.startActivity(intent)
            Toast.makeText(context, "📂 Opening Downloads / Backups", Toast.LENGTH_SHORT).show()
            return
        } catch (e: Exception) {
            Log.w(TAG, "ACTION_VIEW_DOWNLOADS not available", e)
        }

        // 2. Try FileProvider folder intent
        try {
            val uri: Uri = FileProvider.getUriForFile(
                context,
                "${context.packageName}.fileprovider",
                targetDir
            )
            val intent = Intent(Intent.ACTION_VIEW).apply {
                setDataAndType(uri, "*/*")
                addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
                addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
            }
            val chooser = Intent.createChooser(intent, "Open Backups Folder")
            chooser.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
            context.startActivity(chooser)
            return
        } catch (e: Exception) {
            Log.w(TAG, "FileProvider directory intent failed", e)
        }

        Toast.makeText(context, "Backups stored at: ${targetDir.absolutePath}", Toast.LENGTH_LONG).show()
    }

    fun shareBackupFile(context: Context, file: File) {
        if (!file.exists()) {
            Toast.makeText(context, "Backup file not found: ${file.name}", Toast.LENGTH_SHORT).show()
            return
        }
        val uri: Uri = try {
            FileProvider.getUriForFile(
                context,
                "${context.packageName}.fileprovider",
                file
            )
        } catch (e: Exception) {
            Toast.makeText(context, "Failed to share: ${e.message}", Toast.LENGTH_SHORT).show()
            return
        }

        val intent = Intent(Intent.ACTION_SEND).apply {
            type = "application/zip"
            putExtra(Intent.EXTRA_STREAM, uri)
            addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
            addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
        }
        val chooser = Intent.createChooser(intent, "Share Backup Archive")
        chooser.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
        context.startActivity(chooser)
    }

    fun openInExternalReader(context: Context, filePath: String) {
        val file = File(filePath)
        if (!file.exists()) {
            Toast.makeText(context, "File does not exist on device", Toast.LENGTH_SHORT).show()
            return
        }

        scanMediaFile(context, file)

        val uri: Uri = try {
            FileProvider.getUriForFile(
                context,
                "${context.packageName}.fileprovider",
                file
            )
        } catch (e: Exception) {
            Toast.makeText(context, "Failed to share file: ${e.message}", Toast.LENGTH_SHORT).show()
            return
        }

        val mimeType = if (file.name.endsWith(".cbz", true)) "application/x-cbz" else "application/pdf"
        val intent = Intent(Intent.ACTION_VIEW).apply {
            setDataAndType(uri, mimeType)
            addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
            addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
        }

        val chooser = Intent.createChooser(intent, "Open comic in...")
        chooser.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
        context.startActivity(chooser)
    }

    @JvmStatic
    fun downloadAndInstallApk(
        context: Context,
        apkUrl: String,
        onProgress: ((percent: Int) -> Unit)? = null,
        onError: ((error: String) -> Unit)? = null
    ) {
        val executor = Executors.newSingleThreadExecutor()
        val handler = Handler(Looper.getMainLooper())

        handler.post {
            Toast.makeText(context, "Starting APK download...", Toast.LENGTH_SHORT).show()
        }

        executor.execute {
            try {
                val updatesDir = File(context.cacheDir, "updates")
                if (!updatesDir.exists()) {
                    updatesDir.mkdirs()
                }
                val destFile = File(updatesDir, "update.apk")
                if (destFile.exists()) {
                    destFile.delete()
                }

                var currentUrl = apkUrl
                var connection: HttpURLConnection? = null
                var redirectCount = 0
                val maxRedirects = 8

                while (redirectCount < maxRedirects) {
                    val url = URL(currentUrl)
                    connection = url.openConnection() as HttpURLConnection
                    connection.instanceFollowRedirects = true
                    connection.setRequestProperty("User-Agent", "ManhuaExtractor-Updater")
                    connection.connectTimeout = 15000
                    connection.readTimeout = 30000
                    connection.connect()

                    val status = connection.responseCode
                    if (status == HttpURLConnection.HTTP_MOVED_TEMP ||
                        status == HttpURLConnection.HTTP_MOVED_PERM ||
                        status == HttpURLConnection.HTTP_SEE_OTHER ||
                        status == 307 || status == 308
                    ) {
                        val newLocation = connection.getHeaderField("Location")
                        connection.disconnect()
                        if (!newLocation.isNullOrBlank()) {
                            currentUrl = newLocation
                            redirectCount++
                            continue
                        }
                    }
                    break
                }

                if (connection == null || connection.responseCode != 200) {
                    val code = connection?.responseCode ?: -1
                    val err = "Download failed with HTTP code $code"
                    handler.post {
                        Toast.makeText(context, err, Toast.LENGTH_LONG).show()
                        onError?.invoke(err)
                    }
                    return@execute
                }

                val totalLength = connection.contentLength.toLong()
                var downloaded: Long = 0
                var lastProgressPercent = 0

                connection.inputStream.use { input ->
                    destFile.outputStream().use { output ->
                        val buffer = ByteArray(16384)
                        var bytesRead: Int
                        while (input.read(buffer).also { bytesRead = it } != -1) {
                            output.write(buffer, 0, bytesRead)
                            downloaded += bytesRead
                            if (totalLength > 0) {
                                val percent = ((downloaded * 100) / totalLength).toInt()
                                if (percent >= lastProgressPercent + 5 || percent == 100) {
                                    lastProgressPercent = percent
                                    handler.post {
                                        onProgress?.invoke(percent)
                                    }
                                }
                            }
                        }
                    }
                }

                handler.post {
                    Toast.makeText(context, "Download complete. Launching installer...", Toast.LENGTH_SHORT).show()
                    installApk(context, destFile)
                }

            } catch (e: Exception) {
                Log.e(TAG, "Error downloading APK: ${e.message}", e)
                handler.post {
                    val err = "Update failed: ${e.localizedMessage ?: e.message}"
                    Toast.makeText(context, err, Toast.LENGTH_LONG).show()
                    onError?.invoke(err)
                }
            }
        }
    }

    @JvmStatic
    fun installApk(context: Context, apkFile: File) {
        if (!apkFile.exists() || apkFile.length() == 0L) {
            Toast.makeText(context, "APK file not found or empty", Toast.LENGTH_SHORT).show()
            return
        }

        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            if (!context.packageManager.canRequestPackageInstalls()) {
                val settingsIntent = Intent(
                    Settings.ACTION_MANAGE_UNKNOWN_APP_SOURCES,
                    Uri.parse("package:${context.packageName}")
                ).apply {
                    addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
                }
                context.startActivity(settingsIntent)
                Toast.makeText(
                    context,
                    "Please allow 'Install unknown apps' for Manhua Extractor to complete the update.",
                    Toast.LENGTH_LONG
                ).show()
                return
            }
        }

        val apkUri = try {
            FileProvider.getUriForFile(
                context,
                "${context.packageName}.fileprovider",
                apkFile
            )
        } catch (e: Exception) {
            Toast.makeText(context, "Failed to resolve APK URI: ${e.message}", Toast.LENGTH_SHORT).show()
            return
        }

        val installIntent = Intent(Intent.ACTION_VIEW).apply {
            setDataAndType(apkUri, "application/vnd.android.package-archive")
            addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
            addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
        }
        try {
            context.startActivity(installIntent)
        } catch (e: Exception) {
            Log.e(TAG, "Failed to start install intent: ${e.message}", e)
            Toast.makeText(context, "Could not open package installer: ${e.message}", Toast.LENGTH_LONG).show()
        }
    }
}

class AndroidWebAppInterface(private val context: Context) {

    @JavascriptInterface
    fun isAndroidApp(): Boolean = true

    @JavascriptInterface
    fun isDebug(): Boolean {
        return (context.applicationInfo.flags and android.content.pm.ApplicationInfo.FLAG_DEBUGGABLE) != 0
    }

    @JavascriptInterface
    fun downloadAndInstallApk(apkUrl: String) {
        FileUtils.downloadAndInstallApk(context, apkUrl, onProgress = { pct ->
            if (context is MainActivity) {
                context.runOnUiThread {
                    context.notifyUpdateProgress(pct)
                }
            }
        }, onError = { err ->
            if (context is MainActivity) {
                context.runOnUiThread {
                    context.notifyUpdateError(err)
                }
            }
        })
    }

    @JavascriptInterface
    fun installDownloadedApk() {
        val updateFile = File(context.cacheDir, "updates/update.apk")
        if (updateFile.exists() && updateFile.length() > 0L) {
            FileUtils.installApk(context, updateFile)
        }
    }

    @JavascriptInterface
    fun notifyDownloadStarted() {
        DownloadForegroundService.startService(context)
    }

    @JavascriptInterface
    fun openInExternalReader(filePath: String) {
        FileUtils.openInExternalReader(context, filePath)
    }

    @JavascriptInterface
    fun scanMediaFile(filePath: String) {
        FileUtils.scanMediaFile(context, File(filePath))
    }

    @JavascriptInterface
    fun openBackupFolder() {
        FileUtils.openBackupFolder(context)
    }

    @JavascriptInterface
    fun getBackupDirectoryPath(): String {
        return FileUtils.getBackupDirectory(context).absolutePath
    }

    @JavascriptInterface
    fun saveBackupToDevice(filename: String): String {
        val backupDir = FileUtils.getBackupDirectory(context)
        val file = File(backupDir, filename)
        if (file.exists()) {
            val uri = FileUtils.saveZipToPublicDownloads(context, file)
            return if (uri != null) "Saved to Downloads/Manhua/Backups/${file.name}" else "Saved locally"
        }
        return "File not found"
    }

    @JavascriptInterface
    fun shareBackupFile(filename: String) {
        val backupDir = FileUtils.getBackupDirectory(context)
        val file = File(backupDir, filename)
        FileUtils.shareBackupFile(context, file)
    }
}

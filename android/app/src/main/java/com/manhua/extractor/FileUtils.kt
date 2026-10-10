package com.manhua.extractor

import android.content.Context
import android.content.Intent
import android.media.MediaScannerConnection
import android.net.Uri
import android.webkit.JavascriptInterface
import android.widget.Toast
import androidx.core.content.FileProvider
import java.io.File

object FileUtils {

    fun scanMediaFile(context: Context, file: File) {
        if (!file.exists()) return
        val mimeType = if (file.name.endsWith(".cbz", true)) "application/x-cbz" else "application/pdf"
        MediaScannerConnection.scanFile(
            context,
            arrayOf(file.absolutePath),
            arrayOf(mimeType)
        ) { _, _ -> }
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
}

class AndroidWebAppInterface(private val context: Context) {

    @JavascriptInterface
    fun isAndroidApp(): Boolean = true

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
}

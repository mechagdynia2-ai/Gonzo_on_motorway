import 'package:flutter/material.dart';
import 'package:webview_flutter/webview_flutter.dart';

void main() {
  runApp(MaterialApp(
    home: Scaffold(
      body: WebView(
        initialUrl: "https://your-app.onrender.com",  // ← TWÓJ HOST
        javascriptMode: JavascriptMode.unrestricted,
      ),
    ),
  ));
}

import 'dart:typed_data';
import 'package:flutter/material.dart';
import 'package:camera/camera.dart';
import 'package:image/image.dart' as img;
import 'package:http/http.dart' as http;

late List<CameraDescription> cameras;

void main() async {
  WidgetsFlutterBinding.ensureInitialized();
  cameras = await availableCameras();
  runApp(const CameraStreamerApp());
}

class CameraStreamerApp extends StatelessWidget {
  const CameraStreamerApp({super.key});
  @override
  Widget build(BuildContext context) =>
      const MaterialApp(home: ConnectScreen());
}

class ConnectScreen extends StatefulWidget {
  const ConnectScreen({super.key});
  @override
  State<ConnectScreen> createState() => _ConnectScreenState();
}

class _ConnectScreenState extends State<ConnectScreen> {
  final ipController = TextEditingController(text: "192.168.1.100");
  final portController = TextEditingController(text: "5001");

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text("Connect to Server")),
      body: Padding(
        padding: const EdgeInsets.all(20),
        child: Column(
          children: [
            TextField(
                controller: ipController,
                decoration: const InputDecoration(labelText: "Server IP")),
            TextField(
                controller: portController,
                decoration: const InputDecoration(labelText: "Port")),
            const SizedBox(height: 20),
            ElevatedButton(
              onPressed: () {
                final ip = ipController.text;
                final port = portController.text;
                Navigator.push(
                    context,
                    MaterialPageRoute(
                      builder: (_) =>
                          CameraScreen(serverUrl: "http://$ip:$port/frame"),
                    ));
              },
              child: const Text("Connect & Stream"),
            ),
          ],
        ),
      ),
    );
  }
}

class CameraScreen extends StatefulWidget {
  final String serverUrl;
  const CameraScreen({super.key, required this.serverUrl});
  @override
  State<CameraScreen> createState() => _CameraScreenState();
}

class _CameraScreenState extends State<CameraScreen> {
  late CameraController _controller;
  bool _isStreaming = false;

  @override
  void initState() {
    super.initState();
    _controller = CameraController(cameras.first, ResolutionPreset.low,
        enableAudio: false);
    _controller.initialize().then((_) {
      if (!mounted) return;
      setState(() {});
      _controller.startImageStream(_processCameraImage);
    });
  }

  Future<void> _processCameraImage(CameraImage image) async {
    if (_isStreaming) return;
    _isStreaming = true;

    try {
      final width = image.width;
      final height = image.height;

      // Convert YUV420 to RGB image
      final imgRgb = img.Image(width: width, height: height);

      final planeY = image.planes[0].bytes;
      final planeU = image.planes[1].bytes;
      final planeV = image.planes[2].bytes;

      for (int y = 0; y < height; y++) {
        for (int x = 0; x < width; x++) {
          final uvIndex = (y >> 1) * (image.planes[1].bytesPerRow) + (x >> 1);

          final yp = planeY[y * image.planes[0].bytesPerRow + x];
          final up = planeU[uvIndex];
          final vp = planeV[uvIndex];

          int r = (yp + 1.370705 * (vp - 128)).round();
          int g = (yp - 0.698001 * (vp - 128) - 0.337633 * (up - 128)).round();
          int b = (yp + 1.732446 * (up - 128)).round();

          final color = img.ColorRgb8(
            r.clamp(0, 255),
            g.clamp(0, 255),
            b.clamp(0, 255),
          );
          imgRgb.setPixel(x, y, color);
        }
      }

      // Encode to JPEG
      final jpegData = img.encodeJpg(imgRgb, quality: 50);

      final request =
          http.MultipartRequest('POST', Uri.parse(widget.serverUrl));
      request.files.add(http.MultipartFile.fromBytes(
          'frame', Uint8List.fromList(jpegData),
          filename: 'frame.jpg'));
      await request.send();
    } catch (e) {
      debugPrint("Error: $e");
    } finally {
      _isStreaming = false;
    }
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text("Streaming")),
      body: _controller.value.isInitialized
          ? CameraPreview(_controller)
          : const Center(child: CircularProgressIndicator()),
    );
  }
}

import 'dart:convert';
import 'dart:typed_data';
import 'package:flutter/material.dart';
import 'package:camera/camera.dart';
import 'package:http/http.dart' as http;

void main() async {
  WidgetsFlutterBinding.ensureInitialized();
  final cameras = await availableCameras();
  runApp(CamCapApp(cameras: cameras));
}

class CamCapApp extends StatelessWidget {
  final List<CameraDescription> cameras;

  const CamCapApp({Key? key, required this.cameras}) : super(key: key);

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'CamCap',
      theme: ThemeData(primarySwatch: Colors.blue),
      home: ServerInputPage(cameras: cameras),
    );
  }
}

class ServerInputPage extends StatefulWidget {
  final List<CameraDescription> cameras;

  const ServerInputPage({Key? key, required this.cameras}) : super(key: key);

  @override
  State<ServerInputPage> createState() => _ServerInputPageState();
}

class _ServerInputPageState extends State<ServerInputPage> {
  final TextEditingController _ipController = TextEditingController();
  final TextEditingController _portController = TextEditingController();

  void _startStreaming() {
    final ip = _ipController.text.trim();
    final port = _portController.text.trim();
    if (ip.isNotEmpty && port.isNotEmpty) {
      Navigator.push(
        context,
        MaterialPageRoute(
          builder: (_) => CameraStreamPage(
            cameras: widget.cameras,
            serverUrl: 'http://$ip:$port/frame',
          ),
        ),
      );
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Enter Server Info')),
      body: Padding(
        padding: const EdgeInsets.all(16.0),
        child: Column(
          children: [
            TextField(
              controller: _ipController,
              keyboardType: TextInputType.text,
              decoration: const InputDecoration(labelText: 'Server IP'),
            ),
            TextField(
              controller: _portController,
              keyboardType: TextInputType.number,
              decoration: const InputDecoration(labelText: 'Port'),
            ),
            const SizedBox(height: 20),
            ElevatedButton(
              onPressed: _startStreaming,
              child: const Text('Start Camera Stream'),
            ),
          ],
        ),
      ),
    );
  }
}

class CameraStreamPage extends StatefulWidget {
  final List<CameraDescription> cameras;
  final String serverUrl;

  const CameraStreamPage({Key? key, required this.cameras, required this.serverUrl}) : super(key: key);

  @override
  State<CameraStreamPage> createState() => _CameraStreamPageState();
}

class _CameraStreamPageState extends State<CameraStreamPage> {
  late CameraController _controller;
  bool _isStreaming = true;

  @override
  void initState() {
    super.initState();
    _initCamera();
  }

  void _initCamera() async {
    _controller = CameraController(widget.cameras.first, ResolutionPreset.low);
    await _controller.initialize();
    _controller.startImageStream((image) async {
      if (!_isStreaming) return;
      _isStreaming = false;

      try {
        final bytes = image.planes[0].bytes;
        final response = await http.post(
          Uri.parse(widget.serverUrl),
          headers: {'Content-Type': 'application/octet-stream'},
          body: Uint8List.fromList(bytes),
        );
        print('Sent frame: ${response.statusCode}');
      } catch (e) {
        print('Error sending frame: $e');
      }

      await Future.delayed(const Duration(milliseconds: 500));
      _isStreaming = true;
    });

    setState(() {});
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    if (!_controller.value.isInitialized) return const Center(child: CircularProgressIndicator());
    return Scaffold(
      appBar: AppBar(title: const Text('Streaming Camera')),
      body: CameraPreview(_controller),
    );
  }
}

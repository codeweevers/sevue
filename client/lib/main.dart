import 'package:flutter/material.dart';
import 'package:flutter_webrtc/flutter_webrtc.dart';
import 'package:web_socket_channel/web_socket_channel.dart';
import 'dart:convert';

void main() => runApp(const CameraStreamerApp());

class CameraStreamerApp extends StatelessWidget {
  const CameraStreamerApp({super.key});
  @override
  Widget build(BuildContext context) => const MaterialApp(home: ConnectScreen());
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
                      builder: (_) => CameraScreen(serverUrl: "ws://$ip:$port"),
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
  final _localRenderer = RTCVideoRenderer();
  RTCPeerConnection? _peerConnection;
  MediaStream? _localStream;
  WebSocketChannel? _channel;

  @override
  void initState() {
    super.initState();
    _localRenderer.initialize();
    _connect();
  }

  @override
  void dispose() {
    _localRenderer.dispose();
    _peerConnection?.close();
    _channel?.sink.close();
    super.dispose();
  }

  Future<void> _connect() async {
    _channel = WebSocketChannel.connect(Uri.parse(widget.serverUrl));
    _localStream = await navigator.mediaDevices.getUserMedia({'video': true, 'audio': false});
    _localRenderer.srcObject = _localStream;
    _peerConnection = await createPeerConnection({});
    // Use addTrack instead of addStream for Unified Plan
    for (var track in _localStream!.getTracks()) {
      _peerConnection!.addTrack(track, _localStream!);
    }
    _peerConnection!.onIceCandidate = (candidate) {
      _channel!.sink.add(jsonEncode({'type': 'candidate', 'candidate': candidate.toMap()}));
    };
    _channel!.stream.listen((message) async {
      final data = jsonDecode(message);
      if (data['type'] == 'answer') {
        await _peerConnection!.setRemoteDescription(
          RTCSessionDescription(data['sdp'], data['type']),
        );
      } else if (data['type'] == 'candidate') {
        final c = data['candidate'];
        await _peerConnection!.addCandidate(
          RTCIceCandidate(c['candidate'], c['sdpMid'], c['sdpMLineIndex']),
        );
      }
    });
    RTCSessionDescription offer = await _peerConnection!.createOffer();
    await _peerConnection!.setLocalDescription(offer);
    _channel!.sink.add(jsonEncode({'type': 'offer', 'sdp': offer.sdp}));
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text("Streaming (WebRTC)")),
      body: RTCVideoView(_localRenderer),
    );
  }
}

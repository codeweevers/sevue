import 'package:flutter/material.dart';
import 'package:web_socket_channel/web_socket_channel.dart';
import 'package:flutter_webrtc/flutter_webrtc.dart';

void main() async {
  WidgetsFlutterBinding.ensureInitialized();
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
                          CameraScreen(serverUrl: "ws://$ip:$port"),
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
  late RTCPeerConnection _peerConnection;
  late MediaStream _localStream;
  final _localRenderer = RTCVideoRenderer();
  late WebSocketChannel channel;

  @override
  void initState() {
    super.initState();
    _initRenderers();
    _connect();
  }

  Future<void> _initRenderers() async {
    await _localRenderer.initialize();
  }

  Future<void> _connect() async {
    channel = WebSocketChannel.connect(Uri.parse(widget.serverUrl));
    _localStream = await navigator.mediaDevices.getUserMedia({'video': true, 'audio': false});
    _localRenderer.srcObject = _localStream;
    _peerConnection = await createPeerConnection({
      'iceServers': [
        {'urls': 'stun:stun.l.google.com:19302'}
      ]
    });
    _peerConnection.addStream(_localStream);
    _peerConnection.onIceCandidate = (candidate) {
      channel.sink.add({'type': 'candidate', 'candidate': candidate.toMap()});
    };
    channel.stream.listen((message) async {
      // Handle signaling messages (SDP/candidate)
      if (message is Map && message['type'] == 'answer') {
        await _peerConnection.setRemoteDescription(RTCSessionDescription(message['sdp'], message['type']));
      } else if (message is Map && message['type'] == 'candidate') {
        await _peerConnection.addCandidate(RTCIceCandidate(
          message['candidate']['candidate'],
          message['candidate']['sdpMid'],
          message['candidate']['sdpMLineIndex'],
        ));
      }
    });
    RTCSessionDescription offer = await _peerConnection.createOffer();
    await _peerConnection.setLocalDescription(offer);
    channel.sink.add({'type': 'offer', 'sdp': offer.sdp});
  }

  @override
  void dispose() {
    _localRenderer.dispose();
    _peerConnection.close();
    channel.sink.close();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text("Streaming (WebRTC)")),
      body: RTCVideoView(_localRenderer),
    );
  }
}

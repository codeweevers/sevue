// main.dart
import 'dart:convert';
import 'package:flutter/material.dart';
import 'package:flutter_webrtc/flutter_webrtc.dart';
import 'package:web_socket_channel/web_socket_channel.dart';

void main() => runApp(MyApp());

class MyApp extends StatelessWidget {
  const MyApp({super.key});

  @override
  Widget build(BuildContext context) => MaterialApp(home: StreamPage());
}

class StreamPage extends StatefulWidget {
  const StreamPage({super.key});

  @override
  // ignore: library_private_types_in_public_api
  _StreamPageState createState() => _StreamPageState();
}

class _StreamPageState extends State<StreamPage> {
  final _localRenderer = RTCVideoRenderer();
  RTCPeerConnection? _peerConnection;
  MediaStream? _localStream;
  WebSocketChannel? _channel;
  String ip = '';
  String port = '';

  @override
  void initState() {
    super.initState();
    _localRenderer.initialize();
  }

  @override
  void dispose() {
    _localRenderer.dispose();
    _peerConnection?.close();
    _channel?.sink.close();
    super.dispose();
  }

  Future<void> _startWebRTC() async {
    _channel = WebSocketChannel.connect(Uri.parse('ws://$ip:$port'));
    _localStream = await navigator.mediaDevices.getUserMedia({'video': true, 'audio': false});
    _localRenderer.srcObject = _localStream;

    _peerConnection = await createPeerConnection({
      'iceServers': [
        {'urls': 'stun:stun.l.google.com:19302'}
      ]
    });

    _peerConnection!.addStream(_localStream!);

    _peerConnection!.onIceCandidate = (candidate) {
      _channel!.sink.add(
        jsonEncode({'type': 'candidate', 'candidate': candidate.toMap()}),
      );
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
      appBar: AppBar(title: const Text('WebRTC Camera Streamer')),
      body: Padding(
        padding: const EdgeInsets.all(16.0),
        child: Column(children: [
          TextField(
            decoration: const InputDecoration(labelText: 'Server IP (e.g., 192.168.0.100)'),
            onChanged: (value) => ip = value,
          ),
          TextField(
            decoration: const InputDecoration(labelText: 'Port (e.g., 5001)'),
            onChanged: (value) => port = value,
            keyboardType: TextInputType.number,
          ),
          const SizedBox(height: 16),
          ElevatedButton(
            onPressed: _startWebRTC,
            child: const Text('Start WebRTC Streaming'),
          ),
          const SizedBox(height: 16),
          Expanded(child: RTCVideoView(_localRenderer)),
        ]),
      ),
    );
  }
}

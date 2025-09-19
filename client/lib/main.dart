import 'package:flutter/material.dart';
import 'package:jitsi_meet_flutter_sdk/jitsi_meet_flutter_sdk.dart';

void main() {
  runApp(const MyApp());
}

class MyApp extends StatelessWidget {
  const MyApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'Jitsi Meet Flutter SDK Sample',
      theme: ThemeData(
        colorScheme: ColorScheme.fromSeed(seedColor: Colors.deepPurple),
        useMaterial3: true,
      ),
      home: const MyHomePage(title: 'Jitsi Meet Flutter SDK Sample'),
    );
  }
}

class MyHomePage extends StatefulWidget {
  const MyHomePage({super.key, required this.title});
  final String title;

  @override
  State<MyHomePage> createState() => _MyHomePageState();
}

class _MyHomePageState extends State<MyHomePage> {
  final meetingNameController = TextEditingController();
  final jitsiMeet = JitsiMeet();

  @override
  void initState() {
    super.initState();

    // Register Jitsi event listeners

    JitsiMeetEventListener(
      conferenceWillJoin: (url) => _showSnack("Joining meeting..."),
      conferenceJoined: (url) => _showSnack("Joined meeting successfully!"),
      conferenceTerminated: (url, error) =>
          _showSnack("Meeting ended (error: $error)"),
      readyToClose: () => _showSnack("Meeting closed"),
    );
  }

  /// Generate a random meeting name
  void joinMeeting() {
    String roomName = meetingNameController.text.trim();
    if (roomName.isEmpty) {
      _showSnack("Please enter a meeting name");
      return;
    }
    _joinRoom(roomName);
  }

  /// Helper to join room
  void _joinRoom(String roomName) {
    var options = JitsiMeetConferenceOptions(
      serverURL: "https://meet.techclub.co.in",
      room: roomName,
      configOverrides: {
        "startWithAudioMuted": true,
        "startWithVideoMuted": true,
        "subject": "roomName",
      },
      featureFlags: {
        "unsaferoomwarning.enabled": false,
        "security-options.enabled": false,
      },
      userInfo: JitsiMeetUserInfo(
        displayName: "Flutter User",
        email: "user@example.com",
      ),
    );

    jitsiMeet.join(options);
  }

  void _showSnack(String message) {
    ScaffoldMessenger.of(
      context,
    ).showSnackBar(SnackBar(content: Text(message)));
  }

  @override
  void dispose() {
    meetingNameController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        backgroundColor: Theme.of(context).colorScheme.inversePrimary,
        title: Text(widget.title),
      ),
      body: Center(
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: <Widget>[
            // TextField for joining
            SizedBox(
              width: 250,
              height: 50,
              child: TextField(
                controller: meetingNameController,
                decoration: const InputDecoration(
                  border: OutlineInputBorder(),
                  hintText: 'Enter meeting name',
                ),
              ),
            ),
            const SizedBox(height: 20),

            // Join existing meeting button
            SizedBox(
              width: 150,
              height: 50,
              child: FilledButton(
                onPressed: joinMeeting,
                child: const Text("create / Join Meeting"),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

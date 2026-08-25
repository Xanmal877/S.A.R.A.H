#include <WiFi.h>
#include <WebServer.h>

const char* ssid = "SARAH";
const char* password = "SarahRobot";

const int IN1 = 25;
const int IN2 = 26;

WebServer server(80);

void stopMotor() {
  digitalWrite(IN1, LOW);
  digitalWrite(IN2, LOW);
}

void forwardMotor() {
  digitalWrite(IN1, HIGH);
  digitalWrite(IN2, LOW);
}

void backwardMotor() {
  digitalWrite(IN1, LOW);
  digitalWrite(IN2, HIGH);
}

void handleRoot() {
  String page = R"rawliteral(
<!DOCTYPE html>
<html>
<head>
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Sarah Control</title>
</head>
<body>
  <h1>Sarah Control</h1>

  <button onclick="sendCommand('/forward')" style="font-size:30px;">FORWARD</button>
  <br><br>

  <button onclick="sendCommand('/stop')" style="font-size:30px;">STOP</button>
  <br><br>

  <button onclick="sendCommand('/backward')" style="font-size:30px;">BACKWARD</button>

<script>
function sendCommand(cmd) {
  fetch(cmd)
    .then(response => response.text())
    .then(data => console.log(data))
    .catch(error => console.log(error));
}
</script>

</body>
</html>
)rawliteral";

  server.send(200, "text/html", page);
}

void handleForward() {
  forwardMotor();
  Serial.println("FORWARD");
  server.send(200, "text/plain", "OK");
}

void handleBackward() {
  backwardMotor();
  Serial.println("BACKWARD");
  server.send(200, "text/plain", "OK");
}

void handleStop() {
  stopMotor();
  Serial.println("STOP");
  server.send(200, "text/plain", "OK");
}

void setup() {
  Serial.begin(115200);

  pinMode(IN1, OUTPUT);
  pinMode(IN2, OUTPUT);

  stopMotor();

  WiFi.softAP(ssid, password);

  Serial.println("SARAH IS ONLINE");
  Serial.println(WiFi.softAPIP());

  server.on("/", handleRoot);
  server.on("/forward", handleForward);
  server.on("/backward", handleBackward);
  server.on("/stop", handleStop);

  server.begin();
}

void loop() {
  server.handleClient();
}
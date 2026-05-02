/*
 * Smart Home Security System - Arduino UNO Code
 * 
 * Hardware Components:
 * - Arduino UNO R3 (main controller)
 * - ESP32-S3 with OV2640 camera (connected to Arduino via Serial)
 * - Flame Sensor, MQ-2, LDR, Laser+LDR, Servo, Keypad, LED, Buzzer
 * 
 * Communication:
 * - USB Serial (9600 baud) -> Computer running serial_bridge.py -> Flask Server
 * - SoftwareSerial D4/D5 (9600 baud) -> ESP32-S3 Camera Module
 * 
 * The Arduino UNO connects to the computer via USB for sensor data
 * and commands. The ESP32-S3 is connected to Arduino via D4/D5
 * for camera coordination (trigger captures, receive face results).
 * The ESP32-S3 has its own WiFi and sends images to Flask directly.
 * 
 * Pin Map (Arduino UNO):
 * ========================
 * SENSORS:
 *   Flame Sensor     -> D2   (Digital Input)
 *   MQ-2 Smoke       -> A0   (Analog Input, 0-1023)
 *   LDR (Light)      -> A1   (Analog Input, 0-1023)
 *   Laser LDR        -> A2   (Analog Input, 0-1023)
 *
 * ACTUATORS:
 *   Laser Emitter    -> D3   (Digital Output)
 *   Buzzer           -> D7   (Digital Output)
 *   LED              -> D8   (Digital Output)
 *   Servo Motor      -> D9   (PWM Output)
 *
 * ESP32-S3 CAMERA (via SoftwareSerial):
 *   Arduino D4 (TX)  -> ESP32-S3 RX (via 1K+2K voltage divider)
 *   Arduino D5 (RX)  <- ESP32-S3 TX (3.3V OK for Arduino HIGH)
 *
 * KEYPAD (4x4):
 *   Row 1  -> D6     Row 2  -> D10
 *   Row 3  -> D11    Row 4  -> D12
 *   Col 1  -> D13    Col 2  -> A3
 *   Col 3  -> A4     Col 4  -> A5
 *
 * Serial Protocol (USB -> Python Bridge):
 *   Arduino -> Python: SENSORS:{json}  or  KEYPAD:1234  or  FACE:UNKNOWN
 *   Python -> Arduino: CMD:DOOR:1      or  CMD:BUZZER:0
 *                       CMD:LED:1       or  CMD:SERVO:90
 *
 * Serial Protocol (D4/D5 -> ESP32-S3):
 *   Arduino -> ESP32-S3: CAPTURE        (trigger photo)
 *   ESP32-S3 -> Arduino: FACE:OK:name   (authorized face detected)
 *                       FACE:UNKNOWN    (unauthorized person detected)
 *                       CAMERA:READY    (camera initialized)
 *                       WIFI:OK         (WiFi connected)
 */

#include <SoftwareSerial.h>
#include <Keypad.h>
#include <Servo.h>

// ==================== PIN DEFINITIONS ====================
// Sensors
#define FLAME_PIN       2     // Digital - Flame sensor
#define MQ2_PIN         A0    // Analog - Smoke/Gas sensor
#define LDR_PIN         A1    // Analog - Light sensor
#define LASER_LDR_PIN   A2    // Analog - LDR for laser detection

// Actuators
#define LASER_PIN       3     // Digital - Laser emitter
#define BUZZER_PIN      7     // Digital - Buzzer/Alarm
#define LED_PIN         8     // Digital - Status LED
#define SERVO_PIN       9     // PWM - Servo motor (door)

// ESP32-S3 Camera Serial
#define ESP_RX_PIN      5     // Arduino RX <- ESP32-S3 TX
#define ESP_TX_PIN      4     // Arduino TX -> ESP32-S3 RX (via voltage divider)

// ==================== THRESHOLDS ====================
#define MQ2_THRESHOLD     200
#define LDR_THRESHOLD     300
#define LASER_THRESHOLD   100
#define FLAME_DETECT      LOW

// ==================== KEYPAD SETUP ====================
const byte ROWS = 4;
const byte COLS = 4;
char keys[ROWS][COLS] = {
  {'1','2','3','A'},
  {'4','5','6','B'},
  {'7','8','9','C'},
  {'*','0','#','D'}
};
byte rowPins[ROWS] = {6, 10, 11, 12};
byte colPins[COLS] = {13, A3, A4, A5};

Keypad keypad = Keypad(makeKeymap(keys), rowPins, colPins, ROWS, COLS);
Servo doorServo;
SoftwareSerial espSerial(ESP_RX_PIN, ESP_TX_PIN);

// ==================== STATE VARIABLES ====================
bool doorLocked = true;
bool alarmActive = false;
bool ledOn = false;
String keypadBuffer = "";
String inputBuffer = "";
String espInputBuffer = "";
unsigned long lastSensorUpdate = 0;
const unsigned long SENSOR_INTERVAL = 3000;
bool cameraReady = false;

// ==================== SETUP ====================
void setup() {
  Serial.begin(9600);
  Serial.println(F("=== Smart Home Security System ==="));
  Serial.println(F("=== Arduino UNO + ESP32-S3 Cam  ==="));
  
  // Initialize pins
  pinMode(FLAME_PIN, INPUT);
  pinMode(LASER_PIN, OUTPUT);
  pinMode(BUZZER_PIN, OUTPUT);
  pinMode(LED_PIN, OUTPUT);
  
  // Initialize actuators
  digitalWrite(LASER_PIN, HIGH);
  digitalWrite(BUZZER_PIN, LOW);
  digitalWrite(LED_PIN, LOW);
  
  // Initialize servo
  doorServo.attach(SERVO_PIN);
  doorServo.write(0);
  
  // Initialize ESP32-S3 serial
  espSerial.begin(9600);
  
  // Ready indicator
  digitalWrite(LED_PIN, HIGH); delay(200);
  digitalWrite(LED_PIN, LOW); delay(200);
  digitalWrite(LED_PIN, HIGH); delay(200);
  digitalWrite(LED_PIN, LOW);
  
  Serial.println(F("System ready! Waiting for serial bridge..."));
}

// ==================== MAIN LOOP ====================
void loop() {
  unsigned long now = millis();
  
  // Send sensor data every interval
  if (now - lastSensorUpdate >= SENSOR_INTERVAL) {
    lastSensorUpdate = now;
    sendSensorData();
  }
  
  // Check commands from Python bridge (USB Serial)
  checkSerialCommands();
  
  // Check messages from ESP32-S3 camera (SoftwareSerial)
  checkEspSerial();
  
  // Check keypad
  checkKeypad();
  
  // Local alarm check (instant response)
  checkLocalAlarms();
  
  delay(50);
}

// ==================== SEND SENSOR DATA ====================
void sendSensorData() {
  bool flameDetected = (digitalRead(FLAME_PIN) == FLAME_DETECT);
  int smokeLevel = analogRead(MQ2_PIN);
  bool smokeDetected = (smokeLevel > MQ2_THRESHOLD);
  int ldrValue = analogRead(LDR_PIN);
  int laserLdrValue = analogRead(LASER_LDR_PIN);
  bool laserBroken = (laserLdrValue < LASER_THRESHOLD);
  
  // Send to Python bridge
  Serial.print(F("SENSORS:{"));
  Serial.print(F("\"flame\":")); Serial.print(flameDetected ? F("true") : F("false"));
  Serial.print(F(",\"smoke\":")); Serial.print(smokeDetected ? F("true") : F("false"));
  Serial.print(F(",\"smoke_level\":")); Serial.print(smokeLevel);
  Serial.print(F(",\"laser\":")); Serial.print(laserBroken ? F("true") : F("false"));
  Serial.print(F(",\"ldr\":")); Serial.print((ldrValue < LDR_THRESHOLD) ? F("true") : F("false"));
  Serial.print(F(",\"ldr_value\":")); Serial.print(ldrValue);
  Serial.print(F(",\"door\":")); Serial.print(doorLocked ? F("false") : F("true"));
  Serial.print(F(",\"buzzer\":")); Serial.print(alarmActive ? F("true") : F("false"));
  Serial.print(F(",\"led\":")); Serial.print(ledOn ? F("true") : F("false"));
  Serial.println(F("}"));
  
  // Debug
  Serial.print(F("# Flame:")); Serial.print(flameDetected);
  Serial.print(F(" Smoke:")); Serial.print(smokeLevel);
  Serial.print(F(" Laser:")); Serial.println(laserBroken ? F("BROKEN") : F("OK"));
}

// ==================== ESP32-S3 CAMERA COMMUNICATION ====================
void checkEspSerial() {
  while (espSerial.available()) {
    char c = espSerial.read();
    if (c == '\n') {
      processEspMessage(espInputBuffer);
      espInputBuffer = "";
    } else if (c != '\r') {
      espInputBuffer += c;
    }
  }
}

void processEspMessage(String msg) {
  msg.trim();
  Serial.print(F("# [ESP32-S3] ")); Serial.println(msg);
  
  if (msg == F("CAMERA:READY")) {
    cameraReady = true;
    Serial.println(F("# Camera module is ready"));
  }
  else if (msg == F("WIFI:OK")) {
    Serial.println(F("# ESP32-S3 WiFi connected"));
  }
  else if (msg.startsWith(F("FACE:OK:"))) {
    // Authorized face: FACE:OK:John
    String name = msg.substring(8);
    Serial.print(F("FACE:AUTH:")); Serial.println(name);
    Serial.print(F("# Authorized face: ")); Serial.println(name);
  }
  else if (msg == F("FACE:UNKNOWN")) {
    // Unauthorized person detected by camera!
    Serial.println(F("FACE:UNKNOWN"));
    Serial.println(F("# !!! UNAUTHORIZED PERSON DETECTED BY CAMERA !!!"));
    
    // Activate alarm locally
    digitalWrite(BUZZER_PIN, HIGH);
    digitalWrite(LED_PIN, HIGH);
    alarmActive = true;
    ledOn = true;
  }
}

void triggerCapture() {
  if (cameraReady) {
    espSerial.println(F("CAPTURE"));
    Serial.println(F("# Capture triggered on ESP32-S3"));
  }
}

// ==================== USB SERIAL COMMAND PROCESSING ====================
void checkSerialCommands() {
  while (Serial.available()) {
    char c = Serial.read();
    if (c == '\n') {
      processCommand(inputBuffer);
      inputBuffer = "";
    } else if (c != '\r') {
      inputBuffer += c;
    }
  }
}

void processCommand(String cmd) {
  if (!cmd.startsWith("CMD:")) return;
  
  int firstColon = cmd.indexOf(':', 4);
  if (firstColon < 0) return;
  
  String type = cmd.substring(4, firstColon);
  String value = cmd.substring(firstColon + 1);
  
  if (type == F("DOOR")) {
    if (value == F("1") || value == F("true")) unlockDoor();
    else lockDoor();
  }
  else if (type == F("BUZZER")) {
    if (value == F("1") || value == F("true")) {
      digitalWrite(BUZZER_PIN, HIGH); alarmActive = true;
      Serial.println(F("# Buzzer ON (server cmd)"));
    } else {
      digitalWrite(BUZZER_PIN, LOW); alarmActive = false;
      Serial.println(F("# Buzzer OFF (server cmd)"));
    }
  }
  else if (type == F("LED")) {
    if (value == F("1") || value == F("true")) {
      digitalWrite(LED_PIN, HIGH); ledOn = true;
      Serial.println(F("# LED ON (server cmd)"));
    } else {
      digitalWrite(LED_PIN, LOW); ledOn = false;
      Serial.println(F("# LED OFF (server cmd)"));
    }
  }
  else if (type == F("SERVO")) {
    int angle = value.toInt();
    if (angle >= 0 && angle <= 180) {
      doorServo.write(angle);
      Serial.print(F("# Servo angle: ")); Serial.println(angle);
    }
  }
  else if (type == F("KEYPAD_OK")) {
    unlockDoor();
    digitalWrite(BUZZER_PIN, HIGH); delay(100);
    digitalWrite(BUZZER_PIN, LOW); delay(100);
    digitalWrite(BUZZER_PIN, HIGH); delay(100);
    digitalWrite(BUZZER_PIN, LOW);
  }
  else if (type == F("KEYPAD_FAIL")) {
    digitalWrite(BUZZER_PIN, HIGH); delay(500);
    digitalWrite(BUZZER_PIN, LOW);
  }
  else if (type == F("CAPTURE")) {
    // From web UI: trigger camera capture
    triggerCapture();
  }
}

// ==================== LOCAL ALARM CHECKS ====================
void checkLocalAlarms() {
  // Flame detection
  if (digitalRead(FLAME_PIN) == FLAME_DETECT) {
    Serial.println(F("# !!! FIRE DETECTED - LOCAL ALARM !!!"));
    digitalWrite(BUZZER_PIN, HIGH); alarmActive = true;
    triggerCapture();  // Capture image of fire
  }
  
  // Smoke detection
  if (analogRead(MQ2_PIN) > MQ2_THRESHOLD) {
    Serial.println(F("# !!! SMOKE DETECTED - LOCAL ALARM !!!"));
    digitalWrite(BUZZER_PIN, HIGH); alarmActive = true;
    triggerCapture();
  }
  
  // Laser beam broken (intruder)
  if (analogRead(LASER_LDR_PIN) < LASER_THRESHOLD) {
    Serial.println(F("# !!! INTRUDER - LASER BEAM BROKEN !!!"));
    if (!alarmActive) {
      digitalWrite(BUZZER_PIN, HIGH); alarmActive = true;
    }
    triggerCapture();  // Capture image of intruder
  }
}

// ==================== KEYPAD ====================
void checkKeypad() {
  char key = keypad.getKey();
  if (!key) return;
  
  Serial.print(F("# Keypad: ")); Serial.println(key);
  
  if (key == '#') {
    if (keypadBuffer.length() > 0) {
      Serial.print(F("KEYPAD:")); Serial.println(keypadBuffer);
      keypadBuffer = "";
    }
  } else if (key == '*') {
    keypadBuffer = "";
    Serial.println(F("# Keypad cleared"));
  } else if (key == 'A') { lockDoor();
  } else if (key == 'B') { unlockDoor();
  } else if (key == 'C') { toggleAlarm();
  } else if (key == 'D') { toggleLED();
  } else {
    if (keypadBuffer.length() < 8) keypadBuffer += key;
    digitalWrite(BUZZER_PIN, HIGH); delay(50);
    if (!alarmActive) digitalWrite(BUZZER_PIN, LOW);
  }
}

// ==================== HARDWARE CONTROL ====================
void unlockDoor() {
  doorServo.write(90); doorLocked = false;
  Serial.println(F("# Door UNLOCKED"));
}
void lockDoor() {
  doorServo.write(0); doorLocked = true;
  Serial.println(F("# Door LOCKED"));
}
void toggleAlarm() {
  alarmActive = !alarmActive;
  digitalWrite(BUZZER_PIN, alarmActive ? HIGH : LOW);
  Serial.println(alarmActive ? F("# Alarm ON") : F("# Alarm OFF"));
}
void toggleLED() {
  ledOn = !ledOn;
  digitalWrite(LED_PIN, ledOn ? HIGH : LOW);
  Serial.println(ledOn ? F("# LED ON") : F("# LED OFF"));
}

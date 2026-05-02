/*
 * Smart Home Security - ESP32-S3 Camera Module
 * 
 * This code runs on a separate ESP32-S3 board with OV2640 camera
 * that handles face recognition by sending captured frames to
 * the Flask backend via WiFi.
 * 
 * Supported Boards:
 * - ESP32-S3-EYE (Espressif official)
 * - ESP32-S3-WROOM with OV2640 camera module
 * - Generic ESP32-S3 camera boards
 * 
 * The ESP32-S3 connects to WiFi independently and sends
 * captured JPEG images to the Flask server for face detection.
 * 
 * Flash this to ESP32-S3 using Arduino IDE:
 * - Board: "ESP32S3 Dev Module" or "ESP32-S3-EYE"
 * - Upload Speed: 921600
 * - Use external 5V power supply (min 2A)
 * 
 * IMPORTANT: Select the correct camera pin definition below
 * based on your ESP32-S3 board model!
 */

#include "esp_camera.h"
#include <WiFi.h>
#include <HTTPClient.h>

// ==================== WIFI CONFIG ====================
const char* WIFI_SSID = "YOUR_WIFI_SSID";
const char* WIFI_PASS = "YOUR_WIFI_PASSWORD";
const char* SERVER_URL = "http://YOUR_PC_IP:5000";

// ==================== CAMERA PIN DEFINITIONS ====================
// Choose your board model by uncommenting the correct section

// --- OPTION 1: ESP32-S3-EYE (Espressif official board) ---
#define CAMERA_MODEL_ESP32_S3_EYE
// Pin definitions for ESP32-S3-EYE:
#if defined(CAMERA_MODEL_ESP32_S3_EYE)
  #define PWDN_GPIO_NUM     -1
  #define RESET_GPIO_NUM    -1
  #define XCLK_GPIO_NUM     15
  #define SIOD_GPIO_NUM      4
  #define SIOC_GPIO_NUM      5
  #define Y9_GPIO_NUM       16
  #define Y8_GPIO_NUM       17
  #define Y7_GPIO_NUM       18
  #define Y6_GPIO_NUM       12
  #define Y5_GPIO_NUM       11
  #define Y4_GPIO_NUM       10
  #define Y3_GPIO_NUM        9
  #define Y2_GPIO_NUM        8
  #define VSYNC_GPIO_NUM     6
  #define HREF_GPIO_NUM      7
  #define PCLK_GPIO_NUM     13
#endif

// --- OPTION 2: Generic ESP32-S3-WROOM with OV2640 ---
// Uncomment the lines below if you have a generic ESP32-S3 camera board
// #define CAMERA_MODEL_ESP32_S3_WROOM
#if defined(CAMERA_MODEL_ESP32_S3_WROOM)
  #define PWDN_GPIO_NUM     -1
  #define RESET_GPIO_NUM    -1
  #define XCLK_GPIO_NUM     10
  #define SIOD_GPIO_NUM      9
  #define SIOC_GPIO_NUM      8
  #define Y9_GPIO_NUM       11
  #define Y8_GPIO_NUM       12
  #define Y7_GPIO_NUM       13
  #define Y6_GPIO_NUM       14
  #define Y5_GPIO_NUM       15
  #define Y4_GPIO_NUM       16
  #define Y3_GPIO_NUM       17
  #define Y2_GPIO_NUM       18
  #define VSYNC_GPIO_NUM     6
  #define HREF_GPIO_NUM      7
  #define PCLK_GPIO_NUM     21
#endif

// ==================== CAPTURE SETTINGS ====================
unsigned long lastCapture = 0;
const unsigned long CAPTURE_INTERVAL = 5000;  // 5 seconds between captures
bool cameraReady = false;

// ==================== SETUP ====================
void setup() {
  Serial.begin(115200);
  Serial.println("ESP32-S3 Camera Module Starting...");

  // Configure camera
  camera_config_t config;
  config.ledc_channel = LEDC_CHANNEL_0;
  config.ledc_timer = LEDC_TIMER_0;
  config.pin_d0 = Y2_GPIO_NUM;
  config.pin_d1 = Y3_GPIO_NUM;
  config.pin_d2 = Y4_GPIO_NUM;
  config.pin_d3 = Y5_GPIO_NUM;
  config.pin_d4 = Y6_GPIO_NUM;
  config.pin_d5 = Y7_GPIO_NUM;
  config.pin_d6 = Y8_GPIO_NUM;
  config.pin_d7 = Y9_GPIO_NUM;
  config.pin_xclk = XCLK_GPIO_NUM;
  config.pin_pclk = PCLK_GPIO_NUM;
  config.pin_vsync = VSYNC_GPIO_NUM;
  config.pin_href = HREF_GPIO_NUM;
  config.pin_sscb_sda = SIOD_GPIO_NUM;
  config.pin_sscb_scl = SIOC_GPIO_NUM;
  config.pin_pwdn = PWDN_GPIO_NUM;
  config.pin_reset = RESET_GPIO_NUM;
  config.xclk_freq_hz = 20000000;
  config.pixel_format = PIXFORMAT_JPEG;

  // Initialize with appropriate specs
  if (psramFound()) {
    config.frame_size = FRAMESIZE_UXGA;
    config.jpeg_quality = 10;
    config.fb_count = 2;
    Serial.println("PSRAM found - using high resolution");
  } else {
    config.frame_size = FRAMESIZE_SVGA;
    config.jpeg_quality = 12;
    config.fb_count = 1;
    Serial.println("No PSRAM - using standard resolution");
  }

  // Initialize camera
  esp_err_t err = esp_camera_init(&config);
  if (err != ESP_OK) {
    Serial.printf("Camera init FAILED with error 0x%x\n", err);
    Serial.println("Check camera wiring and pin definitions!");
    cameraReady = false;
    return;
  }

  // Set lower resolution for faster face detection
  sensor_t *s = esp_camera_sensor_get();
  s->set_framesize(s, FRAMESIZE_CIF);  // 400x296 for faster processing
  // Flip/mirror if needed (uncomment if image is upside down):
  // s->set_vflip(s, 1);   // Vertical flip
  // s->set_hmirror(s, 1); // Horizontal mirror

  cameraReady = true;
  Serial.println("Camera initialized successfully!");

  // Connect to WiFi
  WiFi.begin(WIFI_SSID, WIFI_PASS);
  Serial.print("Connecting to WiFi");
  int attempts = 0;
  while (WiFi.status() != WL_CONNECTED && attempts < 30) {
    delay(500);
    Serial.print(".");
    attempts++;
  }

  if (WiFi.status() == WL_CONNECTED) {
    Serial.println("\nWiFi connected!");
    Serial.print("IP Address: ");
    Serial.println(WiFi.localIP());
    Serial.print("Server: ");
    Serial.println(SERVER_URL);
  } else {
    Serial.println("\nWiFi connection FAILED!");
    Serial.println("Check SSID/password and 2.4GHz network");
  }
}

// ==================== MAIN LOOP ====================
void loop() {
  // Check WiFi connection
  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("WiFi disconnected - retrying...");
    WiFi.begin(WIFI_SSID, WIFI_PASS);
    delay(5000);
    return;
  }

  // Check camera
  if (!cameraReady) {
    delay(5000);
    return;
  }

  // Capture at interval
  unsigned long now = millis();
  if (now - lastCapture < CAPTURE_INTERVAL) return;
  lastCapture = now;

  captureAndSend();
}

// ==================== CAPTURE AND SEND ====================
void captureAndSend() {
  // Capture image
  camera_fb_t *fb = esp_camera_fb_get();
  if (!fb) {
    Serial.println("Camera capture failed");
    return;
  }

  Serial.printf("Captured: %d bytes\n", fb->len);

  // Send to Flask server for face detection
  HTTPClient http;
  String url = String(SERVER_URL) + "/api/camera/esp32-capture";
  http.begin(url);
  http.addHeader("Content-Type", "image/jpeg");
  http.setTimeout(10000);  // 10 second timeout

  int httpCode = http.POST(fb->buf, fb->len);

  if (httpCode > 0) {
    String response = http.getString();
    Serial.printf("Server response (%d): %s\n", httpCode, response.c_str());

    // Check if unauthorized person detected
    if (response.indexOf("\"authorized\":false") >= 0 ||
        response.indexOf("\"authorized\": false") >= 0) {
      Serial.println("!!! UNAUTHORIZED PERSON DETECTED !!!");
    }
  } else {
    Serial.printf("Upload failed: %s\n", http.errorToString(httpCode).c_str());
  }

  http.end();
  esp_camera_fb_return(fb);  // Free frame buffer
}

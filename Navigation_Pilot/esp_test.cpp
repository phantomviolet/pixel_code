#include "BluetoothSerial.h"

BluetoothSerial SerialBT;

const int VIB1_PIN = 15; // 햅틱1
const int VIB2_PIN = 16; // 햅틱2

void setup() {
  Serial.begin(115200);
  SerialBT.begin("ESP32_Vibrator"); // 블루투스 이름
  Serial.println("ESP32 Ready. Waiting...");

  pinMode(VIB1_PIN, OUTPUT);
  pinMode(VIB2_PIN, OUTPUT);

  digitalWrite(VIB1_PIN, LOW);
  digitalWrite(VIB2_PIN, LOW);
}

void loop() {
  if (SerialBT.available()) {
    char signal = SerialBT.read();
    Serial.print("Received: ");
    Serial.println(signal);

    if (signal == '1') {
      // 햅틱1 진동 500ms
      digitalWrite(VIB1_PIN, HIGH);
      delay(500);
      digitalWrite(VIB1_PIN, LOW);
      Serial.println("Motor 1 Vibrated!");
      SerialBT.println("DONE1");
    } 
    else if (signal == '2') {
      // 햅틱2 진동 500ms
      digitalWrite(VIB2_PIN, HIGH);
      delay(500);
      digitalWrite(VIB2_PIN, LOW);
      Serial.println("Motor 2 Vibrated!");
      SerialBT.println("DONE2");
    }
  }
}

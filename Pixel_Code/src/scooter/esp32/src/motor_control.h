#pragma once
#include <Arduino.h>

void mc_init(int servoPin);
void mc_set_brake_safe();   // 기본 위치(해제)
void mc_set_brake_slow();   // 감속
void mc_set_brake_brake();  // 제동(강)
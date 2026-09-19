# Zygisk AI Runtime —— 备选构建（ndk-build）
#
# 主构建是 native/CMakeLists.txt；本文件供 ndk-build 场景使用（Magisk 模块生态更习惯）。
# 两个构建系统产出的 libai_analyzer.so 必须一致，改动时两边都要同步。
#
# 前置：先由 ../build/scripts/build-gum.sh 构建 Frida-Gum，
#       并构建出 liblsplant.so（必须 SHARED，LGPL-3.0 约束）。
#
# 用法：
#   ndk-build NDK_PROJECT_PATH=. APP_BUILD_SCRIPT=./Android.mk NDK_APPLICATION_MK=./Application.mk

LOCAL_PATH := $(call my-dir)
ZAI_ROOT   := $(LOCAL_PATH)/..
GUM_ABI_DIR := $(ZAI_ROOT)/third_party/frida-gum/17.18.0/build/$(TARGET_ARCH_ABI)

# --- Frida-Gum 预构建静态库 ---
include $(CLEAR_VARS)
LOCAL_MODULE := gum
LOCAL_SRC_FILES := $(GUM_ABI_DIR)/libgum.a
include $(PREBUILT_STATIC_LIBRARY)

# --- LSPlant 预构建共享库（🔴 禁止改为 PREBUILT_STATIC_LIBRARY）---
include $(CLEAR_VARS)
LOCAL_MODULE := lsplant
LOCAL_SRC_FILES := $(GUM_ABI_DIR)/../lsplant/$(TARGET_ARCH_ABI)/liblsplant.so
include $(PREBUILT_SHARED_LIBRARY)

# --- 本工程 ---
include $(CLEAR_VARS)
LOCAL_MODULE := ai_analyzer

LOCAL_CPPFLAGS := -std=c++23 -fvisibility=hidden -fvisibility-inlines-hidden
LOCAL_CPPFLAGS += -DZAI_MODULE_NAME=\"ai_analyzer\"

LOCAL_C_INCLUDES := \
    $(LOCAL_PATH)/include \
    $(ZAI_ROOT) \
    $(ZAI_ROOT)/third_party/frida-gum/17.18.0 \
    $(GUM_ABI_DIR)/include \
    $(ZAI_ROOT)/third_party/lsplant/lsplant/src/main/jni/include

LOCAL_SRC_FILES := \
    $(ZAI_ROOT)/zygisk/module.cpp \
    $(ZAI_ROOT)/zygisk/entry.cpp \
    $(ZAI_ROOT)/zygisk/bootstrap.cpp \
    $(ZAI_ROOT)/runtime/runtime.cpp \
    $(ZAI_ROOT)/runtime/backend/gum/gum_backend.cpp \
    $(ZAI_ROOT)/runtime/backend/art/art_backend.cpp \
    $(ZAI_ROOT)/runtime/backend/art/lsplant_adapter.cpp \
    $(ZAI_ROOT)/runtime/manager/hook_manager.cpp \
    $(ZAI_ROOT)/runtime/manager/memory_manager.cpp \
    $(ZAI_ROOT)/runtime/manager/process_manager.cpp \
    src/common/log.cpp

LOCAL_STATIC_LIBRARIES := gum
LOCAL_SHARED_LIBRARIES := lsplant
LOCAL_LDLIBS := -llog -ldl

include $(BUILD_SHARED_LIBRARY)

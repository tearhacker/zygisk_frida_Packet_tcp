# ndk-build 全局配置
#
# 首发只做 arm64-v8a：LSPlant 的 ART Hook 在 arm64 上最成熟，
# 且 Frida-Gum 交叉编译链在 arm64 上依赖最少。

APP_ABI := arm64-v8a
APP_PLATFORM := android-30
APP_STL := c++_static
APP_CPPFLAGS := -fexceptions -frtti -Wno-gnu-string-literal-operator-template
APP_OPTIM := release

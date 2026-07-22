cmake_minimum_required(VERSION 3.15)
project(RangeTintNative LANGUAGES CXX)

find_package(Nuke REQUIRED)

add_library(range_tint_native SHARED range_tint_native.cpp)
target_link_libraries(range_tint_native PRIVATE Nuke::NDK)
target_compile_features(range_tint_native PRIVATE cxx_std_14)
target_compile_definitions(range_tint_native PRIVATE NOMINMAX _USE_MATH_DEFINES)
set_target_properties(range_tint_native PROPERTIES PREFIX "")

#include <DDImage/ViewerContext.h>
#include <DDImage/Vector2.h>

#include <cstddef>

using DD::Image::Vector2;
using DD::Image::ViewerContext;

// Read-only bridge used through Python's ctypes. It does not draw, install
// callbacks, create nodes, or retain pointers owned by Nuke.
extern "C" __declspec(dllexport)
int range_tint_viewer_transform(double* out, int count)
{
  if (out == nullptr || count < 16 || DD::Image::activeViewerContext == nullptr)
    return 0;

  const ViewerContext* const_context = DD::Image::activeViewerContext();
  if (const_context == nullptr)
    return 0;

  ViewerContext* context = const_cast<ViewerContext*>(const_context);
  ViewerContext::ViewerWindowFormatContext& format_context =
    context->viewerWindowFormatContext();

  const DD::Image::Format& format = format_context.format;
  const Vector2 p00 = ViewerContext::convertFromViewerToFormat(
    format_context, Vector2(0.0f, 0.0f));
  const Vector2 p10 = ViewerContext::convertFromViewerToFormat(
    format_context, Vector2(100.0f, 0.0f));
  const Vector2 p01 = ViewerContext::convertFromViewerToFormat(
    format_context, Vector2(0.0f, 100.0f));

  float pan_x = 0.0f;
  float pan_y = 0.0f;
  float zoom_x = 1.0f;
  float zoom_y = 1.0f;
  ViewerContext::getViewerWindowPanZoom(
    format_context, pan_x, pan_y, zoom_x, zoom_y);

  out[0] = static_cast<double>(format.x());
  out[1] = static_cast<double>(format.y());
  out[2] = static_cast<double>(format.r());
  out[3] = static_cast<double>(format.t());
  out[4] = static_cast<double>(p00.x);
  out[5] = static_cast<double>(p00.y);
  out[6] = static_cast<double>(p10.x);
  out[7] = static_cast<double>(p10.y);
  out[8] = static_cast<double>(p01.x);
  out[9] = static_cast<double>(p01.y);
  out[10] = static_cast<double>(pan_x);
  out[11] = static_cast<double>(pan_y);
  out[12] = static_cast<double>(zoom_x);
  out[13] = static_cast<double>(zoom_y);
  out[14] = static_cast<double>(format.pixel_aspect());
  out[15] = format_context.ignoreFormatPixelApsect ? 1.0 : 0.0;
  return 1;
}

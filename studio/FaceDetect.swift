import Foundation
import Vision
import ImageIO
let paths=Array(CommandLine.arguments.dropFirst())
var result:[String:Any]=[:]
for path in paths {
 do {
  guard let source=CGImageSourceCreateWithURL(URL(fileURLWithPath:path) as CFURL,nil),let image=CGImageSourceCreateImageAtIndex(source,0,nil) else{throw NSError(domain:"image",code:1)}
  let request=VNDetectFaceRectanglesRequest()
  request.usesCPUOnly=true
  try VNImageRequestHandler(cgImage:image,options:[:]).perform([request])
  let faces=request.results ?? []
  let boxes=faces.map { o -> [Double] in
   let b=o.boundingBox
   return [Double(b.minX),Double(1-b.maxY),Double(b.width),Double(b.height)]
  }
  // Head tilt in degrees (0 = upright); used to skip sideways faces for thumbnails.
  let rolls=faces.map { o -> Double in (o.roll?.doubleValue ?? 0)*180/Double.pi }
  result[path]=["width":image.width,"height":image.height,"faces":boxes,"rolls":rolls]
 } catch {result[path]=["error":error.localizedDescription]}
}
let data=try JSONSerialization.data(withJSONObject:result,options:[.sortedKeys])
FileHandle.standardOutput.write(data)

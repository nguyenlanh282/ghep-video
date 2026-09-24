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
  let boxes=(request.results ?? []).map { o -> [Double] in
   let b=o.boundingBox
   return [Double(b.minX),Double(1-b.maxY),Double(b.width),Double(b.height)]
  }
  result[path]=["width":image.width,"height":image.height,"faces":boxes]
 } catch {result[path]=["error":error.localizedDescription]}
}
let data=try JSONSerialization.data(withJSONObject:result,options:[.sortedKeys])
FileHandle.standardOutput.write(data)

import Foundation
import Vision
import AppKit
import ImageIO
while let path = readLine() {
 do {
  let started=Date()
  let source=CGImageSourceCreateWithURL(URL(fileURLWithPath:path) as CFURL,nil)!
  let full=CGImageSourceCreateImageAtIndex(source,0,nil)!
  let crop=full.cropping(to:CGRect(x:320,y:250,width:320,height:320))!
  let handler=VNImageRequestHandler(cgImage:crop,options:[:])
  let request=VNRecognizeTextRequest()
  request.recognitionLevel = .fast
  request.revision = VNRecognizeTextRequestRevision3
  request.usesLanguageCorrection = false
  request.recognitionLanguages = ["en-US"]
  request.minimumTextHeight = 0
  try handler.perform([request])
  let parts=(request.results ?? []).map { ob -> [String:Any] in
    let c=ob.topCandidates(3)
    return ["candidates":c.map {["text":$0.string,"confidence":$0.confidence]},"x":ob.boundingBox.minX,"y":ob.boundingBox.minY,"w":ob.boundingBox.width,"h":ob.boundingBox.height]
  }
  let result:[String:Any] = ["parts":parts,"seconds":Date().timeIntervalSince(started)]
  let data=try JSONSerialization.data(withJSONObject:result,options:[.sortedKeys]);print(String(data:data,encoding:.utf8)!);fflush(stdout)
 } catch {print("{\"error\":\"OCR failed\"}");fflush(stdout)}
}

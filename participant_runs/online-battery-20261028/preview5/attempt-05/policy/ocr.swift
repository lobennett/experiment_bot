import Foundation
import Vision
import AppKit
while let path = readLine() {
 do {
  let started=Date()
  let handler=VNImageRequestHandler(url:URL(fileURLWithPath:path),options:[:])
  let request=VNRecognizeTextRequest()
  request.recognitionLevel = .accurate
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

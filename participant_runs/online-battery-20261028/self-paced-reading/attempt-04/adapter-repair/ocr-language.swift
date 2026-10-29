import Foundation
import Vision
import AppKit
let url=URL(fileURLWithPath:CommandLine.arguments[1])
let handler=VNImageRequestHandler(url:url,options:[:])
let request=VNRecognizeTextRequest()
request.recognitionLevel = .accurate
request.usesLanguageCorrection = true
request.minimumTextHeight = 0.0
request.recognitionLanguages = ["en-US"]
try handler.perform([request])
let results=(request.results ?? []).compactMap { item -> [String:Any]? in
    guard let candidate=item.topCandidates(1).first else {return nil}
    return ["text":candidate.string,"confidence":candidate.confidence,"bbox":[item.boundingBox.minX,item.boundingBox.minY,item.boundingBox.width,item.boundingBox.height]]
}
let data=try JSONSerialization.data(withJSONObject:results,options:[.sortedKeys])
print(String(data:data,encoding:.utf8)!)

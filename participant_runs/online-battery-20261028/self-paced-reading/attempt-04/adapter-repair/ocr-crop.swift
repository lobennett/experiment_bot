import Foundation
import Vision
import AppKit
let url=URL(fileURLWithPath:CommandLine.arguments[1])
let src=NSImage(contentsOf:url)!
var rect=CGRect(origin:.zero,size:src.size)
let image=src.cgImage(forProposedRect:&rect,context:nil,hints:nil)!
let cropped=image.cropping(to:CGRect(x:20,y:70,width:240,height:100))!
let handler=VNImageRequestHandler(cgImage:cropped,options:[:])
let request=VNRecognizeTextRequest()
request.recognitionLevel = .accurate
request.usesLanguageCorrection = false
try handler.perform([request])
let results=(request.results ?? []).compactMap { item -> [String:Any]? in
    guard let candidate=item.topCandidates(1).first else {return nil}
    return ["text":candidate.string,"confidence":candidate.confidence,"bbox":[item.boundingBox.minX,item.boundingBox.minY,item.boundingBox.width,item.boundingBox.height]]
}
let data=try JSONSerialization.data(withJSONObject:results,options:[.sortedKeys])
print(String(data:data,encoding:.utf8)!)

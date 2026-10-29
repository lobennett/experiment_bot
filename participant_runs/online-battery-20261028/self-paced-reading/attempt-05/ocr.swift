import Foundation
import Vision
import AppKit
let url=URL(fileURLWithPath:CommandLine.arguments[1])
func recognize(_ handler:VNImageRequestHandler) throws -> [[String:Any]] {
    let request=VNRecognizeTextRequest()
    request.recognitionLevel = .accurate
    request.usesLanguageCorrection = false
    try handler.perform([request])
    return (request.results ?? []).compactMap { item -> [String:Any]? in
        guard let candidate=item.topCandidates(1).first else{return nil}
        return ["text":candidate.string,"confidence":candidate.confidence,"bbox":[item.boundingBox.minX,item.boundingBox.minY,item.boundingBox.width,item.boundingBox.height]]
    }
}
var results=try recognize(VNImageRequestHandler(url:url,options:[:]))
if results.isEmpty {
    // This run's observed canvas word band; no supplied words or task state.
    // Full frames are retained, and multi-line instructions use full-frame OCR.
    let source=NSImage(contentsOf:url)!
    var rect=CGRect(origin:.zero,size:source.size)
    let image=source.cgImage(forProposedRect:&rect,context:nil,hints:nil)!
    let scaleX=Double(image.width)/800.0, scaleY=Double(image.height)/600.0
    let band=CGRect(x:20*scaleX,y:70*scaleY,width:760*scaleX,height:110*scaleY)
    if let cropped=image.cropping(to:band) {
        results=try recognize(VNImageRequestHandler(cgImage:cropped,options:[:]))
        for i in results.indices {results[i]["region"]="observed_word_band"}
    }
}
let data=try JSONSerialization.data(withJSONObject:results,options:[.sortedKeys])
print(String(data:data,encoding:.utf8)!)

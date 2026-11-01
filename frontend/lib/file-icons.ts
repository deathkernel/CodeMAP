import { Code2, FileCode2, FileJson, FileText } from "lucide-react";

export function getFileIcon(path: string) {
  const extension = path.split(".").pop()?.toLowerCase();
  if (["json", "jsonc"].includes(extension || "")) return FileJson;
  if (["md", "txt", "mdx"].includes(extension || "")) return FileText;
  if (["py", "js", "jsx", "ts", "tsx", "java", "go", "rs", "cpp", "c", "cs"].includes(extension || "")) return Code2;
  return FileCode2;
}

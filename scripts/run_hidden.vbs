If WScript.Arguments.Count > 0 Then
    Dim script : script = WScript.Arguments(0)
    Dim shell : Set shell = CreateObject("WScript.Shell")
    shell.Run "powershell.exe -WindowStyle Hidden -NonInteractive -ExecutionPolicy Bypass -File """ & script & """", 0, False
End If

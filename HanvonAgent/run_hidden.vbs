' HanvonAgent — Console penceresini gizle
' Kullanım: cscript.exe run_hidden.vbs "C:\path\to\app.exe"

Set objArgs = WScript.Arguments
If objArgs.Count < 1 Then
    WScript.Echo "Kullanım: cscript.exe run_hidden.vbs <exe_path>"
    WScript.Quit 1
End If

exePath = objArgs(0)

' Exe dosyasının var olup olmadığını kontrol et
Set fso = CreateObject("Scripting.FileSystemObject")
If Not fso.FileExists(exePath) Then
    WScript.Echo "Hata: Dosya bulunamadı: " & exePath
    WScript.Quit 1
End If

' Exe'yi gizli modda çalıştır (0 = hidden window)
Set objShell = CreateObject("WScript.Shell")
objShell.Run exePath, 0, False

WScript.Quit 0

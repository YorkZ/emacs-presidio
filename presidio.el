;;; presidio.el --- Emacs integration for placeholder_anonymizer  -*- lexical-binding: t; -*-

;; Copyright © 2025 York Zhao

;; Author: York Zhao <gtdplatform@gmail.com>
;; Version: 0.1
;; Keywords: convenience, tools
;; Package-Requires: ((emacs "26.1"))

;; This file is NOT part of GNU Emacs.

;; This program is free software; you can redistribute it and/or modify it under
;; the terms of the GNU General Public License as published by the Free Software
;; Foundation; either version 3, or (at your option) any later version.
;;
;; This program is distributed in the hope that it will be useful, but WITHOUT
;; ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS
;; FOR A PARTICULAR PURPOSE. See the GNU General Public License for more
;; details.
;;
;; You should have received a copy of the GNU General Public License along with
;; GNU Emacs; see the file COPYING. If not, write to the Free Software
;; Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301,
;; USA.

;;; Commentary:
;;
;; This package provides two interactive commands to anonymize and deanonymize
;; text using a Python placeholder anonymizer script distributed alongside it.
;;
;; Usage:
;;
;; 1. Run `M-x presidio-anonymize-region' on a selected region containing text
;;    with sensitive PII. This will replace the region with anonymized placeholders,
;;    using a JSON mapping file to store original values.
;;
;; 2. After externally revising the anonymized text, select the revised text and run
;;    `M-x presidio-deanonymize-region' to restore the original PII from the JSON
;;    mapping file.
;;
;; By default, the JSON mapping file is stored under
;; `presidio-placeholder-mapping-file' (~/.cache/presidio_mapping.json).
;;
;; Python dependencies (must be installed):
;;   pip install presidio_analyzer presidio_anonymizer
;;   python -m spacy download en_core_web_lg
;;

;;; Code:

(require 'json)

(defvar presidio-script "presidio-placeholder-anonymizer"
  "Name of the Python script used for anonymizing/deanonymizing text.
The script is assumed to be in the same directory as this Emacs Lisp file.")

(defvar presidio-placeholder-mapping-file
  (expand-file-name "presidio_mapping.json" "~/.cache/")
  "Path to the JSON file where entity mappings for placeholders are stored.
This JSON file is updated or read each time an anonymization or
deanonymization is performed.")

(defconst presidio--directory
  (file-name-directory
   (or load-file-name
       ;; If `load-file-name' is nil, try to locate the package in `load-path'.
       (locate-library "presidio")))
  "Directory from which the `presidio.el' package is loaded.
Used to resolve the location of `presidio-script'.")

(defun presidio--script-path ()
  "Return the full path to the Python script named by `presidio-script'.
This script is assumed to be located in `presidio--directory'."
  (expand-file-name presidio-script presidio--directory))

;;;###autoload
(defun presidio-anonymize-region (start end)
  "Anonymize the text in the region from START to END.
Replace the selected text with anonymized placeholders. This function calls
the Python script in `anonymize' mode, capturing JSON output which contains
the `anonymized_text' field to insert back into the buffer. The entity mapping
is updated in `presidio-placeholder-mapping-file'."
  (interactive "r")
  (let* ((script-path (presidio--script-path))
         (temp-buffer (get-buffer-create " *presidio-anonymize-output*"))
         (exit-code (call-process-region
                     start end
                     script-path        ; Program to invoke
                     nil                ; Don't delete region
                     temp-buffer        ; Send stdout here
                     nil                ; No redisplay
                     "anonymize"
                     "--entity-mapping-file"
                     presidio-placeholder-mapping-file)))
    (unless (eq exit-code 0)
      (error "Error calling anonymizer script. Exit code: %s" exit-code))
    (let ((anonymized-text
           (with-current-buffer temp-buffer
             (goto-char (point-min))
             (alist-get 'anonymized_text
                        (json-parse-buffer :object-type 'alist)))))
      ;; Replace selected text with anonymized text
      (delete-region start end)
      (insert anonymized-text))
    (kill-buffer temp-buffer)))

;;;###autoload
(defun presidio-deanonymize-region (start end)
  "Deanonymize the text in the region from START to END.
Placeholders in the selected text are replaced with the original PII by calling
the Python script in `deanonymize' mode, which reads the mapping file specified
by `presidio-placeholder-mapping-file' and returns `deanonymized_text' JSON."
  (interactive "r")
  (let* ((script-path (presidio--script-path))
         (temp-buffer (get-buffer-create " *presidio-deanonymize-output*"))
         (exit-code (call-process-region
                     start end
                     script-path
                     nil
                     temp-buffer
                     nil
                     "deanonymize"
                     "--entity-mapping-file"
                     presidio-placeholder-mapping-file)))
    (unless (eq exit-code 0)
      (error "Error calling deanonymizer script. Exit code: %s" exit-code))
    (let ((deanonymized-text
           (with-current-buffer temp-buffer
             (goto-char (point-min))
             (alist-get 'deanonymized_text
                        (json-parse-buffer :object-type 'alist)))))
      ;; Replace selected text with deanonymized text
      (delete-region start end)
      (insert deanonymized-text))
    (kill-buffer temp-buffer)))


(provide 'presidio)

;;; presidio.el ends here

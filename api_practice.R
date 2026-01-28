# Install if you haven't yet
# install.packages(c("httr2", "jsonlite")) 

# Execute query and save response as object
library(httr2)
library(jsonlite)

# Create request object
req = request("https://reqres.in/api/users/2") |>
  req_headers(`x-api-key` = "reqres-free-v1") |>
  req_method("GET")

# Execute request and store result as object
# Use req_error to prevent automatic error stopping
resp = req |>
  req_error(is_error = function(resp) FALSE) |>
  req_perform()

# Check status
cat("Status code:", resp$status_code, "\n") # 200 = success

# Return response as a JSON (already parsed as R list)
if (resp$status_code == 200) {
  json_data = resp_body_json(resp)
  print(json_data)
} else {
  cat("Error response:\n")
  print(resp_body_string(resp))
}

# Note: resp_body_json() already returns an R list, so no need for fromJSON()

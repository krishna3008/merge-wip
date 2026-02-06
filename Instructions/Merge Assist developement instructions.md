Think yourself as an expert in Python, Docker, GitLab, EKS and Terraform
Create a an app to assist and merge the MRs in GitLab
This app will be deployed in EKS cluster and will be used to merge the MRs in GitLab
This app also will be provided a docker approach to deploy all the Pods in a system/EC2 etc., if needed.
The app consists of following parts
Frontend UI web app to provide the view of progress and logs to monitor
Backend is the actual service apps, it consists of following components
Expect Merge Assist is an user to which the project access is provided which will be used for the backend program
Watcher:- Wathces the GitLab Project for MRs to which it assigned as a reviewer or Assignee and add the details to a table dedicated to the project
Listner:- Listens to the web calls whenever the user is assigned to a MR either as a reviewer or assigne records the details to the 
Database:- Stores the details of the MRs and the status of the merge
WorkerPOD:- This is the actual worker which does the service.
    This is created for. each project seperately.
    It has the following capabilities
        1. First Read the details of the MRs from the database
        2. For each MR, check if the MR is ready to be merged
            a. Check if the pipeline is successful
            b. Check if the MR is approved to merge
            c. Check if the MR is assigned to the user
            d. Gather the labels of the MR
            e. If all are true, then add the workflow label "Merge Assist: Recognised for Merge"
            f. If not ready, update the status in the database and add the reason for not being ready in the form of a commend and add label "Merge Assist: Not Ready for Merge" add the counter as 1 in DB if more than 3 strikes are reached MR will be rejected and label "Merge Assist: Rejected" will be added and remove the label "Merge Assist: Not Ready for Merge" thus remove from the DB and add a comment in the MR about the rejection
            g. This MR can be debugged and assigned once it's ready to merge again
        3. If the assinged MRs are ready to merge, we have two scenarios only one MR is Ready for Merge or multiple MRs are ready to merge
            a. If only one MR is ready to merge, then we will check the MR is mergeable by checking is it up to date with the target branch 
                i. if not, use the gitlab Rebase API to rebase the MR with the target branch thus a pipeline might trigget
                ii. Agent need to wait for the pipeline to success (can use the API to check the status of the pipeline and wait for the pipeline to success)
                iii. Once the pipeline is success, and MR is Green (Ready for merge by GitLab) then add the label "Merge Assist: Ready to Merge"
                iv. Use the GitLab Merge API to merge the MR with the target branch
                v. Once the MR is merged, remove the label "Merge Assist: Ready to Merge" and update the status in the database and add the comment that the MR is merged by Merge Assist
            b. If multiple MRs are ready to merge, then we will check the MRs are mergeable by checking is it up to date with the target branch.
                i. In this case we follow a batching approach, we will merge the MRs in batches of 5 (batch size can be configurable during project onboarding and can update later also)
                ii. Create a batch branch from the target branch if not exists. If exists, delete the branch from remote and local, prune local repo and create a fresh batch branch from the target branch
                iii. Pick the first 5 MRs from the list of MRs that are ready to merge and add them to the batch branch (Use the GitLab Merge API to merge the MR with the batch branch), we can use the timestamp of the label to find the order of the MRs so we can provide first come first serve order.
                iv. Once the batch is successfully created, create the MR with it to the same target branch and add the label "Merge Assist: Batch Merge Request". This MR won't be merged, we use it to check the pipeline for all the MRs in the batch
                v. Add the comment in the MRs that are part of the batch that Merge Assist is working on this batch at an MR (MRid) and will merge once the pipeline is success
                vi. Once the pipeline is success then update the status in the database and add the label to the original MRs that are part of the batch as "Merge Assist: Ready to Merge"
                vii. For each MR in the batch, use the GitLab Merge API to merge the MR with the target branch by rebasing the MR with the target branch using API, this might trigger a pipeline but we verified in the batch MR, so we can force merge the MR with the target branch using API.
                viii. Once the MR is merged, remove the label "Merge Assist: Ready to Merge" and update the status in the database and add the comment that the MR is merged by Merge Assist
The Front End gather the details of the each project from the DB
We can select the project in the front end from drop down.
if the project is onboarded for more than one target branch then a target branch drop down will be shown to select the target branch
W.R.T the selected project and target branch, the front end will show the list of MRs that are ready to merge, not ready to merge, waiting for batch merge, batch merge in progress, batch merge failed, merge failed, merged etc.,
We can select the MRs that are ready to merge and can provide the MR a priority label it needed, if a label is added then the MR will be placed at the top of the order of the MRs that are Recognised for Merge, Can provide the priority w.r.t batch size allowed only 5 MRs can be merged in a batch, not more than that. Also this access will be given only to particular users
Show the logs each project if asked to show what's happenining in the POD about the project.

Have a health check for the each pod such that if the pod is unhealthy then it should be restarted. if not worked alert the Project Owners and Tool Admins
You can refer the https://gitlab.com/marge-org/marge-bot fort the worker POD and merger part.

Create a ReadME and architecture diagram for the Merge Assist tool, to understand the tool better.
Provide an option to USE AI if needed to debug the issues in the tool config for the project, this expects an AI token to be proved which will be saved as part of the secrets. This AI will be used only for debugging purpose. Provide the comments to be added in the MRs for which the tool got in trouble

Also create a layer for the the users authentication and authorization, so that we can provide access to the users based on their roles and permissions. 
Create a usage of secret manager to store the secrets like API tokens, DB credentials etc., 
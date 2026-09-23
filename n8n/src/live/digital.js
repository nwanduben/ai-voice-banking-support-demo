const c = ctx();
const p = rowsOf('Read Digital Access').find((x) => x.customer_id === c.session.customer_id);
if (!p) return result(fail('NOT_FOUND', "I can't see a mobile banking profile for you. You can register in the ENTIN app with your account number.", []));
const data = { app_status: p.app_status, device_linked: yes(p.device_linked), otp_last_status: p.otp_last_status, otp_channel: p.otp_channel };
let say;
if (p.app_status === 'locked') {
  if (tierRank(c.session.tier) < 2) return result(ok({ app_status: 'needs_full_verification' }, "I can see there's an issue with your mobile banking access. To tell you more I need to fully verify you.", ['verify_caller']));
  say = "Your mobile banking profile is locked after too many wrong attempts. I can't unlock it on this call, but you can reset it yourself in the app with 'Forgot password', or visit any branch with a valid ID.";
} else if (!yes(p.device_linked)) say = "It looks like you're logging in on a new phone. The app will ask you to link the new device. Follow those steps and it should work.";
else if (p.otp_last_status === 'dnd_blocked') say = "Our messages to your number are being blocked by Do-Not-Disturb on your line. Ask your network to allow transactional messages, or switch your OTP to email in the app.";
else if (['failed', 'delayed'].includes(p.otp_last_status)) say = "There's been a delay delivering messages to your network. Please wait a few minutes and try again.";
else say = 'Everything looks normal on your mobile banking profile.';
return result(ok(data, say));

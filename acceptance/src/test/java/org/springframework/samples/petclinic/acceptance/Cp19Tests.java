package org.springframework.samples.petclinic.acceptance;

import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

/** cp19 daily-limit: reject creating an owner once 100+ owners have been created today (429).
 *  Create 100 (all dated today by default), then the 101st is rejected. */
@Tag("cp19")
class Cp19Tests extends AcceptanceBase {

	@Test
	void coreRejectsOverDailyLimit() throws Exception {
		createMany(100);
		createOwner(ownerNode()).andExpect(status().isTooManyRequests());
	}
}

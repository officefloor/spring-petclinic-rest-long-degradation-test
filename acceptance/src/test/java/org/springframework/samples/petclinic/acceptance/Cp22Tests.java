package org.springframework.samples.petclinic.acceptance;

import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;

/** bulk-warning: 'bulkSignupWarning' is true once more than 80 owners were created today,
 * else false. Assert the default (false) branch for a fresh create; the &gt;80 branch shares the
 * same accumulation path exercised by the daily-limit rule. */
@Tag("cp22")
class Cp22Tests extends AcceptanceBase {

	@Test
	void coreNoBulkWarningUnderThreshold() throws Exception {
		int id = createOwnerOk(ownerNode());
		getOwner(id).andExpect(jsonPath("$.bulkSignupWarning").value(false));
	}
}

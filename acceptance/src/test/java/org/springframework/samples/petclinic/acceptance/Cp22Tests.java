package org.springframework.samples.petclinic.acceptance;

import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;

/** cp22 bulk-warning: When more than 80 owners have already been created today, include 'bulkSignupWarning' true... */
@Tag("cp22")
class Cp22Tests extends AcceptanceBase {

	@Test
	void coreBulkWarningFalseNormally() throws Exception {
		int id = createOwnerOk(ownerNode());
		getOwner(id).andExpect(jsonPath("$.bulkSignupWarning").value(false)); // TODO: true when >80 today
	}
}

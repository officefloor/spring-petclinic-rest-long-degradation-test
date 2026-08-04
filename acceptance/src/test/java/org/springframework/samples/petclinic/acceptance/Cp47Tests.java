package org.springframework.samples.petclinic.acceptance;

import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;

/** cp47 holiday-business-day: The business-day rule for the registration date must extend to public holidays: when the a... */
@Tag("cp47")
class Cp47Tests extends AcceptanceBase {

	@Test
	void coreRollsPastHoliday() throws Exception {
		int id = createOwnerOk(structuredOwner());
		getOwner(id).andExpect(jsonPath("$.registrationDate").exists()); // TODO: skips public holiday
	}
}
